from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, get_current_approved_business, get_current_user
from api.validation import clamp_description, clamp_title
from core.business_categories import resolve_category_group
from core.tags import infer_tags
from db.accounts import (
    create_user_event,
    delete_user_event,
    get_user_event,
    list_user_events_for_business,
    update_user_event,
)
from db.business_profiles import (
    create_profile,
    get_profile_by_id,
    get_profile_id_for_owner,
    get_profile_row_for_owner,
    list_active_profiles,
    profile_to_public_dict,
    update_profile_for_owner,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/business", tags=["business"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class UserEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    start_date: str = Field(min_length=10, max_length=10)
    start_time: str | None = Field(None, max_length=20)
    end_time: str | None = Field(None, max_length=20)
    location_label: str | None = Field(None, max_length=200)
    venue_name: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=300)
    tags: list[str] = Field(default_factory=list)
    category: str | None = Field(None, max_length=100)


class UserEventOut(BaseModel):
    model_config = {"extra": "ignore"}

    id: int
    business_id: int
    business_profile_id: str | None = None
    title: str
    description: str | None
    start_date: str
    start_time: str | None
    end_time: str | None
    location_label: str | None
    venue_name: str | None = None
    address: str | None = None
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    created_at: str
    updated_at: str


def _parse_tags_cell(raw: Any) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    try:
        p = json.loads(raw)
        if not isinstance(p, list):
            return []
        return [str(x).strip() for x in p if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        return []


def _merge_manual_and_inferred_tags(title: str, description: str, manual: list[str]) -> list[str]:
    cleaned = [t.strip() for t in manual if t and str(t).strip()]
    merged = set(infer_tags(title, description)) | set(cleaned)
    return sorted(merged)


def _normalize_event_payload(body: UserEventCreate) -> dict[str, str | None]:
    title = clamp_title(body.title, 120)
    if not title:
        raise HTTPException(status_code=400, detail="Title required")
    desc = clamp_description(body.description, 2000)
    if not desc or not str(desc).strip():
        raise HTTPException(status_code=400, detail="Description required")
    sd = body.start_date.strip()
    if not _DATE_RE.match(sd):
        raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")

    loc = clamp_title(body.location_label, 200) if body.location_label else None
    vn = clamp_title(body.venue_name, 200) if body.venue_name else None
    ad = clamp_title(body.address, 300) if body.address else None
    if not any([loc, vn, ad]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of location_label, venue_name, or address",
        )

    return {
        "title": title,
        "description": desc,
        "start_date": sd,
        "start_time": body.start_time.strip() if body.start_time else None,
        "end_time": body.end_time.strip() if body.end_time else None,
        "location_label": loc,
        "venue_name": vn,
        "address": ad,
    }


def _row_to_out(row: dict) -> UserEventOut:
    bpid = row.get("business_profile_id")
    bpid_s = str(bpid).strip() if bpid is not None and str(bpid).strip() else None
    return UserEventOut(
        id=int(row["id"]),
        business_id=int(row["business_id"]),
        business_profile_id=bpid_s,
        title=str(row["title"]),
        description=row.get("description"),
        start_date=str(row["start_date"]),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        location_label=row.get("location_label"),
        venue_name=row.get("venue_name"),
        address=row.get("address"),
        tags=_parse_tags_cell(row.get("tags")),
        category=str(row.get("category") or "").strip() or None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _can_modify_event(user: CurrentUser, event: dict) -> bool:
    if user.role == "admin":
        return True
    return user.role == "business" and int(event["business_id"]) == user.id


@router.post("/events", response_model=UserEventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    body: UserEventCreate,
    user: Annotated[CurrentUser, Depends(get_current_approved_business)],
) -> UserEventOut:
    p = _normalize_event_payload(body)
    merged = _merge_manual_and_inferred_tags(
        p["title"] or "",
        p["description"] or "",
        body.tags,
    )
    tags_json = json.dumps(merged)
    category = body.category.strip() if body.category and body.category.strip() else None
    profile_id = get_profile_id_for_owner(user.id)

    eid = create_user_event(
        business_id=user.id,
        title=p["title"] or "",
        description=p["description"],
        start_date=p["start_date"] or "",
        start_time=p["start_time"],
        end_time=p["end_time"],
        location_label=p["location_label"],
        venue_name=p.get("venue_name"),
        address=p.get("address"),
        tags_json=tags_json,
        category=category,
        business_profile_id=profile_id,
    )
    row = get_user_event(eid)
    assert row is not None
    logger.info("user_event created id=%s business_id=%s", eid, user.id)
    return _row_to_out(dict(row))


@router.get("/events", response_model=list[UserEventOut])
def list_my_events(
    user: Annotated[CurrentUser, Depends(get_current_approved_business)],
) -> list[UserEventOut]:
    rows = list_user_events_for_business(user.id)
    return [_row_to_out(dict(r)) for r in rows]


@router.put("/events/{event_id}", response_model=UserEventOut)
def update_event(
    event_id: int,
    body: UserEventCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserEventOut:
    row = get_user_event(event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not _can_modify_event(user, row):
        raise HTTPException(status_code=403, detail="Not allowed to edit this event")
    if user.role == "business" and user.status != "approved":
        raise HTTPException(status_code=403, detail="Business not approved")
    p = _normalize_event_payload(body)
    merged = _merge_manual_and_inferred_tags(
        p["title"] or "",
        p["description"] or "",
        body.tags,
    )
    tags_json = json.dumps(merged)
    category = body.category.strip() if body.category and body.category.strip() else None
    profile_id = get_profile_id_for_owner(user.id)

    if not update_user_event(
        event_id,
        title=p["title"] or "",
        description=p["description"],
        start_date=p["start_date"] or "",
        start_time=p["start_time"],
        end_time=p["end_time"],
        location_label=p["location_label"],
        venue_name=p.get("venue_name"),
        address=p.get("address"),
        tags_json=tags_json,
        category=category,
        business_profile_id=profile_id,
    ):
        raise HTTPException(status_code=500, detail="Update failed")
    updated = get_user_event(event_id)
    assert updated is not None
    logger.info("user_event updated id=%s by user_id=%s", event_id, user.id)
    return _row_to_out(dict(updated))


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_event(
    event_id: int,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    row = get_user_event(event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not _can_modify_event(user, row):
        raise HTTPException(status_code=403, detail="Not allowed to delete this event")
    if user.role == "business" and user.status != "approved":
        raise HTTPException(status_code=403, detail="Business not approved")
    if not delete_user_event(event_id):
        raise HTTPException(status_code=500, detail="Delete failed")
    logger.info("user_event deleted id=%s by user_id=%s", event_id, user.id)


# --- Public business profiles (structured listings) ---


class BusinessProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8000)
    category: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=500)
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=200)


class BusinessProfileOut(BaseModel):
    id: str
    name: str
    description: str
    category: str
    category_group: str
    tags: list[str] = Field(default_factory=list)
    phone: str | None = None
    website: str | None = None
    address: str | None = None
    city: str
    is_active: bool
    created_at: str


class BusinessProfileDetailOut(BusinessProfileOut):
    upcoming_events: list[UserEventOut]


class BusinessProfileUpsert(BaseModel):
    """Owner create/update body (dashboard)."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8000)
    category: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=40)
    website: str | None = Field(None, max_length=500)
    address: str | None = Field(None, max_length=500)
    city: str | None = Field(None, max_length=200)
    is_active: bool = True


def _merge_profile_tags(name: str, description: str) -> list[str]:
    return sorted(set(infer_tags(name, description)))


def _coerce_profile_fields(
    *,
    name: str,
    description: str,
    category: str,
    phone: str | None,
    website: str | None,
    address: str | None,
    city: str | None,
) -> tuple[str, str, str, str, str, str | None, str | None, str | None, str]:
    n = clamp_title(name, 200)
    desc = clamp_description(description, 8000)
    if not n or not str(n).strip():
        raise HTTPException(status_code=400, detail="name required")
    if not desc or not str(desc).strip():
        raise HTTPException(status_code=400, detail="description required")
    cat_raw = category.strip() if category else ""
    if not cat_raw:
        raise HTTPException(status_code=400, detail="category required")
    group = resolve_category_group(cat_raw)
    if not group:
        raise HTTPException(status_code=400, detail="category required")
    tags = _merge_profile_tags(n, desc)
    tags_json = json.dumps(tags)
    ph = clamp_title(phone, 40) if phone else None
    web = (website or "").strip() or None
    addr = clamp_title(address, 500) if address else None
    city_out = (city or "").strip() or "Lake Havasu"
    city_out = clamp_title(city_out, 200) or "Lake Havasu"
    return n, desc, cat_raw, group, tags_json, ph, web, addr, city_out


@router.get("/me", response_model=BusinessProfileOut)
def get_my_business_profile(
    user: Annotated[CurrentUser, Depends(get_current_approved_business)],
) -> BusinessProfileOut:
    row = get_profile_row_for_owner(user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="No business profile yet")
    return BusinessProfileOut(**profile_to_public_dict(row))


@router.put("/me", response_model=BusinessProfileOut)
def upsert_my_business_profile(
    body: BusinessProfileUpsert,
    user: Annotated[CurrentUser, Depends(get_current_approved_business)],
    response: Response,
) -> BusinessProfileOut:
    n, desc, cat_raw, group, tags_json, ph, web, addr, city_out = _coerce_profile_fields(
        name=body.name,
        description=body.description,
        category=body.category,
        phone=body.phone,
        website=body.website,
        address=body.address,
        city=body.city,
    )
    existing = get_profile_row_for_owner(user.id)
    if existing is None:
        pid = create_profile(
            owner_business_id=user.id,
            name=n,
            description=desc,
            category=cat_raw,
            category_group=group,
            tags_json=tags_json,
            phone=ph,
            website=web,
            address=addr,
            city=city_out,
            is_active=body.is_active,
        )
        response.status_code = status.HTTP_201_CREATED
        logger.info("business_profile created via PUT /me id=%s owner=%s", pid, user.id)
    else:
        ok = update_profile_for_owner(
            user.id,
            name=n,
            description=desc,
            category=cat_raw,
            category_group=group,
            tags_json=tags_json,
            phone=ph,
            website=web,
            address=addr,
            city=city_out,
            is_active=body.is_active,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Update failed")
        response.status_code = status.HTTP_200_OK
        pid = str(existing["id"])
        logger.info("business_profile updated via PUT /me id=%s owner=%s", pid, user.id)

    row = get_profile_by_id(pid)
    assert row is not None
    return BusinessProfileOut(**profile_to_public_dict(row))


@router.post("/create", response_model=BusinessProfileOut, status_code=status.HTTP_201_CREATED)
def create_business_profile(
    body: BusinessProfileCreate,
    user: Annotated[CurrentUser, Depends(get_current_approved_business)],
) -> BusinessProfileOut:
    if get_profile_row_for_owner(user.id) is not None:
        raise HTTPException(status_code=409, detail="Business profile already exists for this account")
    name, desc, cat_raw, group, tags_json, phone, website, address, city = _coerce_profile_fields(
        name=body.name,
        description=body.description,
        category=body.category,
        phone=body.phone,
        website=body.website,
        address=body.address,
        city=body.city,
    )

    pid = create_profile(
        owner_business_id=user.id,
        name=name,
        description=desc,
        category=cat_raw,
        category_group=group,
        tags_json=tags_json,
        phone=phone,
        website=website,
        address=address,
        city=city,
    )
    row = get_profile_by_id(pid)
    assert row is not None
    logger.info("business_profile created id=%s owner=%s", pid, user.id)
    return BusinessProfileOut(**profile_to_public_dict(row))


@router.get("/list", response_model=list[BusinessProfileOut])
def list_business_profiles(
    limit: int = Query(100, ge=1, le=500),
) -> list[BusinessProfileOut]:
    rows = list_active_profiles(limit=limit)
    return [BusinessProfileOut(**profile_to_public_dict(r)) for r in rows]


@router.get("/{profile_id:uuid}", response_model=BusinessProfileDetailOut)
def get_business_profile(profile_id: UUID) -> BusinessProfileDetailOut:
    row = get_profile_by_id(str(profile_id))
    if row is None or not int(row.get("is_active") or 0):
        raise HTTPException(status_code=404, detail="Business not found")
    base = BusinessProfileOut(**profile_to_public_dict(row))
    uid = int(row["owner_business_id"])
    ev_rows = list_user_events_for_business(uid)
    today_iso = date.today().isoformat()
    upcoming = [
        _row_to_out(dict(r))
        for r in ev_rows
        if str(r.get("start_date") or "") >= today_iso
    ]
    upcoming.sort(key=lambda e: (e.start_date, e.title))
    return BusinessProfileDetailOut(**base.model_dump(), upcoming_events=upcoming)
