from __future__ import annotations

import json
import logging
import math
import os
import re
import hashlib
import time
from pathlib import Path
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional runtime dependency
    OpenAI = None

from api.rate_limit import RateLimitMiddleware
from api.routers import admin_routes, auth, business_routes

from core.calendar_filters import include_in_homepage_calendar_lists
from core.ai_helper import fallback_generic_suggestions, generate_suggestions, should_use_ai
from core.discover import get_fallback_rows, get_popular, get_today, get_weekend
from core.intent_map import parse_intent
from core.query_expand import expand_query, match_rows_for_queries, should_expand
from core.search_rank import rank_search_results
from core.serialize import (
    MISSING_TIME_SORT,
    coalesce_str,
    finalize_api_list,
    homepage_calendar_sort_key,
    time_sort_value,
)
from core.user_event_map import map_user_event_row_to_item_payload
from db.accounts import (
    get_business_by_id,
    get_user_event_with_profile_fields,
    list_user_event_payloads_for_public,
)
from db.activities import (
    ActivityInput,
    SlotInput,
    build_event_embedding_text,
    delete_activity,
    get_event_click_counts,
    get_ai_clicked_weights,
    increment_activity_click,
    increment_activity_view,
    ingest_activity,
    list_expanded_slot_payloads,
    list_pending_activities,
    log_ai_interaction,
    record_ai_click,
    set_activity_status,
)
from db.database import count_events_by_source, get_item_payload_by_id, init_db, list_events, list_items
from db.submissions import (
    clear_submission_featured,
    create_submission,
    delete_submission,
    find_duplicate_submission_id,
    increment_submission_click,
    increment_submission_view,
    list_notifications_feed,
    list_approved_submission_payloads,
    list_pending_submissions,
    list_submissions,
    set_submission_featured,
    update_submission_status,
)

LIMIT_DEFAULT = 100
LIMIT_MIN = 1
LIMIT_MAX = 200
TRACK_DEDUP_WINDOW_SEC_VIEW = 600.0
TRACK_DEDUP_WINDOW_SEC_CLICK = 600.0
ENABLE_SEED_DATA = True
WEIGHTS = {
    "click": 1.5,
    "popularity": 0.3,
    "recency": 0.7,
    "semantic": 0.65,
}
TOTAL_BOOST_CAP = 1.5
TEST_QUERIES = [
    "kids sports",
    "live music",
    "nightlife",
    "family events",
    "free events",
]

logger = logging.getLogger(__name__)
_track_seen: dict[str, float] = {}
_embedding_cache: dict[str, list[float]] = {}
_seed_cache: list[dict[str, Any]] | None = None


class SearchAISection(BaseModel):
    suggestions: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    results: list[dict[str, Any]] = Field(default_factory=list)
    ai: SearchAISection | None = None


class DiscoverResponse(BaseModel):
    today: list[dict[str, Any]] = Field(default_factory=list)
    weekend: list[dict[str, Any]] = Field(default_factory=list)
    popular: list[dict[str, Any]] = Field(default_factory=list)


class SubmitRequest(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    category: str
    start_date: str | None = None
    location: str = "Lake Havasu"


class SubmitResponse(BaseModel):
    success: bool
    id: str | None = None
    duplicate: bool = False


class SubmitActivitySlot(BaseModel):
    start_time: str
    end_time: str
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    date: str | None = None
    recurring: bool = False


class SubmitActivityRequest(BaseModel):
    title: str
    location: str
    category: str = "events"
    tags: list[str] = Field(default_factory=list)
    time_slots: list[SubmitActivitySlot] = Field(default_factory=list)
    description: str = ""


class TrackRequest(BaseModel):
    id: str = Field(..., min_length=1)


class NotificationFeedItem(BaseModel):
    id: str
    event_ref: str
    title: str
    type: str
    start_date: str
    source: str
    is_featured: bool = False
    featured_until: str = ""
    created_at: str = ""
    updated_at: str = ""


class NotificationFeedResponse(BaseModel):
    items: list[NotificationFeedItem] = Field(default_factory=list)


class AIRecommendRequest(BaseModel):
    query: str = Field(..., min_length=1)


class AIRecommendation(BaseModel):
    id: str
    score: float
    reason: str


class AIClickRequest(BaseModel):
    query: str = Field(..., min_length=1)
    clicked_id: str = Field(..., min_length=1)


def _sanitize_ai_suggestions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return fallback_generic_suggestions()
    out = [str(x).strip() for x in value if x is not None and str(x).strip()]
    return out[:3] if out else fallback_generic_suggestions()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Lake Havasu Discovery API",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],
    allow_origin_regex=r"http://localhost(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)


def _is_valid_admin_token_header(header_value: str | None) -> bool:
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected:
        return False
    if not isinstance(header_value, str):
        return False
    prefix = "Bearer "
    if not header_value.startswith(prefix):
        return False
    provided = header_value[len(prefix) :].strip()
    return bool(provided) and provided == expected


@app.middleware("http")
async def enforce_admin_token(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path.startswith("/admin/"):
        if not _is_valid_admin_token_header(request.headers.get("Authorization")):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return await call_next(request)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(admin_routes.router)
app.include_router(business_routes.router)

_WEEKDAY_ORDER = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_iso_date(value: str | None) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _event_date_span(event: dict) -> tuple[date | None, date | None]:
    start = _parse_iso_date(event.get("start_date"))
    end = _parse_iso_date(event.get("end_date"))
    if start is not None and end is None:
        end = start
    return start, end


def _upcoming_weekend_bounds(today: date) -> tuple[date, date]:
    wd = today.weekday()
    if wd <= 3:
        fri = today + timedelta(days=4 - wd)
    elif wd == 4:
        fri = today
    else:
        fri = today - timedelta(days=wd - 4)
    sun = fri + timedelta(days=2)
    return fri, sun


def _all_events() -> list[dict]:
    return list_events(source=None)


def _upcoming_event_payloads() -> list[dict]:
    today = date.today()
    picked: list[dict] = []
    for e in _all_events():
        start, _ = _event_date_span(e)
        if start is None:
            continue
        if start >= today:
            picked.append(e)
    return picked


_HOME_EVENTS_LIMIT = 10


def _crawler_items_for_query(
    item_type: str | None,
    source: str | None,
) -> list[dict]:
    return list_items(item_type=item_type or None, source=source or None)


def _combined_read_rows(item_type: str | None, source: str | None) -> list[dict]:
    """Crawler `items` plus approved `user_events` where filters allow."""
    t = item_type
    src = source
    if src == "user":
        u = list_user_event_payloads_for_public() + list_approved_submission_payloads()
        if t in ("recurring", "program"):
            return []
        if t in (None, "event"):
            return u
        return []
    if t in ("recurring", "program"):
        return _crawler_items_for_query(t, src)
    crawl = _crawler_items_for_query(t, src)
    if t in (None, "event"):
        return crawl + list_user_event_payloads_for_public() + list_approved_submission_payloads()
    return crawl


def _all_calendar_event_payloads() -> list[dict]:
    """All dated calendar events: crawled + user-submitted."""
    return list_events(source=None) + list_user_event_payloads_for_public() + list_approved_submission_payloads()


def _normalize_submit_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        s = str(t).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:12]


def _tracking_now() -> float:
    return time.monotonic()


def _client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _tracking_should_increment(
    *,
    action: str,
    submission_id: str,
    request: Request,
) -> bool:
    now = _tracking_now()
    max_window = max(TRACK_DEDUP_WINDOW_SEC_VIEW, TRACK_DEDUP_WINDOW_SEC_CLICK)
    cutoff = now - max_window
    stale_keys = [k for k, ts in _track_seen.items() if ts < cutoff]
    for k in stale_keys:
        _track_seen.pop(k, None)

    window = TRACK_DEDUP_WINDOW_SEC_VIEW if action == "view" else TRACK_DEDUP_WINDOW_SEC_CLICK
    ip = _client_ip_from_request(request)
    key = f"{ip}:{submission_id}:{action}"
    last = _track_seen.get(key)
    if last is not None and (now - last) < window:
        return False
    _track_seen[key] = now
    return True


def _is_junk_title(title: str) -> bool:
    t = " ".join(title.strip().lower().split())
    if len(t) < 5:
        return True
    if re.fullmatch(r"[\W\d_]+", t):
        return True
    if re.fullmatch(r"[a-z]{1,4}", t):
        return True
    spam_tokens = {"test", "asdf", "12345"}
    if t in spam_tokens:
        return True
    return False


def _events_for_ai_context(*, limit: int = 75) -> list[dict[str, Any]]:
    rows = _combined_read_rows(None, None) + list_expanded_slot_payloads()
    normalized = finalize_api_list(rows if isinstance(rows, list) else [], False)
    candidates = [r for r in normalized if str(r.get("id") or "").strip()]

    # Keep context reasonably fresh/time-aware before handing to model.
    def key(row: dict[str, Any]) -> tuple[int, str]:
        sd = str(row.get("start_date") or "")
        has_date = 0 if sd else 1
        return (has_date, sd)

    candidates.sort(key=key)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        rid = str(row.get("id") or "").strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        deduped.append(row)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def remove_seed_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if not e.get("is_seed")]


def _seed_file_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "seed_events.json"


def _load_seed_events() -> list[dict[str, Any]]:
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache
    path = _seed_file_path()
    if not path.exists():
        _seed_cache = []
        return _seed_cache
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _seed_cache = []
        return _seed_cache
    if not isinstance(raw, list):
        _seed_cache = []
        return _seed_cache
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        title = str(item.get("title") or "").strip() or sid
        description = str(item.get("description") or "").strip()
        category = str(item.get("category") or "").strip().lower()
        location = str(item.get("location") or "").strip() or "Lake Havasu City"
        popularity = int(item.get("popularity") or 1)
        event_time = str(item.get("event_time") or "").strip()
        tags = [t for t in re.split(r"[^a-z0-9]+", f"{category} {title}".lower()) if len(t) >= 3][:8]
        row: dict[str, Any] = {
            "id": sid,
            "event_ref": sid,
            "title": title,
            "description": description,
            "category": category,
            "tags": tags,
            "location": location,
            "location_label": location,
            "source": "seed",
            "is_seed": bool(item.get("is_seed", True)),
            "view_count": 0,
            "click_count": max(0, popularity),
        }
        if event_time:
            row["start_date"] = event_time
            row["end_date"] = event_time
            row["is_active_now"] = False
        out.append(row)
    _seed_cache = out
    return out


def _parse_event_datetime_for_filter(row: dict[str, Any]) -> datetime | None:
    # Prefer end date/time when available so multi-day events stay eligible
    # until they actually pass.
    preferred = [str(row.get("end_date") or "").strip(), str(row.get("start_date") or "").strip()]
    for raw in preferred:
        if not raw:
            continue
        dt = _parse_start_datetime(raw)
        if dt is not None:
            return dt
        try:
            d = date.fromisoformat(raw[:10])
            return datetime(d.year, d.month, d.day)
        except ValueError:
            continue
    return None


def _filter_stale_ai_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    kept: list[dict[str, Any]] = []
    removed_example: dict[str, str] | None = None
    removed_count = 0
    for row in events:
        dt = _parse_event_datetime_for_filter(row)
        if dt is None:
            kept.append(row)
            continue
        if dt < cutoff:
            removed_count += 1
            if removed_example is None:
                removed_example = {
                    "id": str(row.get("id") or ""),
                    "title": str(row.get("title") or ""),
                    "start_date": str(row.get("start_date") or ""),
                    "end_date": str(row.get("end_date") or ""),
                }
            continue
        kept.append(row)

    stats = {
        "total_events_before_filter": len(events),
        "total_events_after_filter": len(kept),
        "filtered_out_count": removed_count,
        "removed_stale_example": removed_example,
    }
    return kept, stats


def _format_for_ai(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in events[:200]:
        out.append(
            {
                "id": str(e.get("id") or ""),
                "title": str(e.get("title") or ""),
                "description": str(e.get("description") or ""),
                "category": str(e.get("category") or ""),
                "tags": e.get("tags") if isinstance(e.get("tags"), list) else [],
                "start": str(e.get("start_date") or ""),
                "end": str(e.get("end_date") or ""),
                "location": str(e.get("location") or e.get("location_label") or ""),
                "is_active_now": bool(e.get("is_active_now") or False),
            }
        )
    return out


def _local_ai_rank(query: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower().strip()) if t]
    requires_now = any(t in {"now", "open", "live"} for t in tokens)
    out: list[dict[str, Any]] = []
    for e in events:
        score = 0.0
        cat = str(e.get("category") or "").lower()
        tags = [str(t).lower() for t in (e.get("tags") or []) if isinstance(t, str)]
        title = str(e.get("title") or "").lower()
        active = bool(e.get("is_active_now"))
        if active:
            score += 0.5
        if requires_now and active:
            score += 0.4
        tag_hits = sum(1 for t in tokens if t in tags)
        score += min(0.3, 0.08 * tag_hits)
        if any(t == cat for t in tokens):
            score += 0.2
        if any(t and t in title for t in tokens):
            score += 0.1
        if requires_now and not active:
            score -= 0.1
        if score <= 0:
            continue
        reason_parts: list[str] = []
        if active:
            reason_parts.append("happening now")
        if tag_hits > 0:
            reason_parts.append(f"matches {tag_hits} tag(s)")
        if any(t == cat for t in tokens):
            reason_parts.append(f"fits {cat}")
        reason = ", ".join(reason_parts) if reason_parts else "relevant match"
        out.append({"id": str(e.get("id") or ""), "score": float(min(1.0, max(0.0, score))), "reason": reason})
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:5]


def _parse_ai_response_json(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
    except json.JSONDecodeError:
        # Try to extract a JSON array if model wrapped it in prose/fences.
        m = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, list):
                    return [p for p in parsed if isinstance(p, dict)]
            except json.JSONDecodeError:
                return []
    return []


def has_openai_key() -> bool:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key and key.startswith("sk-"))


def get_embedding(text: str, *, cache_key: str | None = None) -> list[float] | None:
    value = (text or "").strip()
    if not value or OpenAI is None:
        return None
    if cache_key:
        cached = _embedding_cache.get(cache_key)
        if isinstance(cached, list) and cached:
            return cached
    if not has_openai_key():
        return None
    try:
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=value,
        )
        data = getattr(resp, "data", None)
        if not data:
            return None
        emb = getattr(data[0], "embedding", None)
        if isinstance(emb, list) and emb:
            if cache_key:
                _embedding_cache[cache_key] = emb
            return emb
        return None
    except Exception:
        return None


def _embedding_debug_reason() -> str:
    if OpenAI is None:
        return "openai_package_missing"
    if not has_openai_key():
        return "missing_openai_key"
    try:
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input="test",
        )
        data = getattr(resp, "data", None)
        if data and getattr(data[0], "embedding", None):
            return "ok"
        return "empty_embedding_response"
    except Exception as exc:
        text = str(exc).lower()
        short = str(exc).strip().replace("\n", " ")[:180]
        if "429" in text or "quota" in text or "rate limit" in text:
            return f"rate_limit_or_quota: {short}"
        if "401" in text or "invalid api key" in text or "incorrect api key" in text:
            return f"auth_error: {short}"
        if "timeout" in text:
            return f"timeout: {short}"
        return f"error:{type(exc).__name__}: {short}"


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    if size <= 0:
        return 0.0
    dot = sum(float(a[i]) * float(b[i]) for i in range(size))
    norm_a = math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(size)))
    norm_b = math.sqrt(sum(float(b[i]) * float(b[i]) for i in range(size)))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize_signal(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return max(0.0, min(1.0, value / max_value))


def _recency_signal(start_raw: str, now: datetime) -> float:
    start_dt = _parse_start_datetime(start_raw)
    if start_dt is None:
        return 0.0
    delta_hours = (start_dt - now).total_seconds() / 3600.0
    # Very old items should not get a recency boost.
    if delta_hours < -24.0:
        return 0.0
    # Exponential decay keeps near-term items meaningful while avoiding flat zeros.
    if delta_hours >= 0.0:
        return max(0.0, min(1.0, math.exp(-delta_hours / 72.0)))
    return max(0.0, min(1.0, math.exp(-abs(delta_hours) / 48.0)))


def _parse_start_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def apply_weighted_rank_boosts(
    query: str,
    items: list[dict[str, Any]],
    *,
    start_lookup: dict[str, str],
    event_text_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    clicked_map = get_ai_clicked_weights(query)
    click_counts = get_event_click_counts()
    now = datetime.utcnow()
    max_click_signal = max(clicked_map.values()) if clicked_map else 0.0
    max_popularity = float(max(click_counts.values())) if click_counts else 0.0
    query_key = f"q:{query.strip().lower()}"
    query_embedding = get_embedding(query, cache_key=query_key)
    boosted: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        rid = str(row.get("id") or "").strip()
        try:
            base_score = float(row.get("score") or 0.0)
        except (TypeError, ValueError):
            base_score = 0.0

        click_signal = _normalize_signal(float(clicked_map.get(rid, 0.0)), max_click_signal)
        popularity_signal = _normalize_signal(float(click_counts.get(rid, 0)), max_popularity)
        recency_signal = _recency_signal(start_lookup.get(rid, ""), now)

        semantic_signal = 0.0
        text = event_text_lookup.get(rid, "")
        if query_embedding and text:
            event_key = f"e:{rid}" if rid else f"e:{hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()}"
            event_embedding = get_embedding(text, cache_key=event_key)
            semantic_signal = max(0.0, min(1.0, cosine_similarity(query_embedding, event_embedding)))

        click_component = click_signal * float(WEIGHTS["click"])
        popularity_component = popularity_signal * float(WEIGHTS["popularity"])
        recency_component = recency_signal * float(WEIGHTS["recency"])
        semantic_component = semantic_signal * float(WEIGHTS["semantic"])
        added = click_component + popularity_component + recency_component + semantic_component

        row["score"] = base_score + min(TOTAL_BOOST_CAP, added)
        row["_score_components"] = {
            "base": round(base_score, 6),
            "click": round(click_component, 6),
            "popularity": round(popularity_component, 6),
            "recency": round(recency_component, 6),
            "semantic": round(semantic_component, 6),
        }
        boosted.append(row)
    return boosted


@app.get("/items")
def get_items(
    item_type: str | None = Query(
        None,
        alias="type",
        description="Item kind: event | recurring | program (omit for all types)",
    ),
    source: str | None = Query(None, description="Filter by crawler source"),
    weekday: str | None = Query(
        None,
        description="For recurring: filter by weekday name (e.g. Monday)",
    ),
    limit: int = Query(LIMIT_DEFAULT, ge=LIMIT_MIN, le=LIMIT_MAX),
    expand: bool = Query(
        False,
        description="If true, return full payload_json-style dicts (legacy).",
    ),
) -> list[dict]:
    """Stored items with optional filters; sorted (start_date, start_time, title)."""
    t = item_type.strip() if item_type else None
    src = source.strip() if source else None
    wd = weekday.strip() if weekday else None
    allowed = ("event", "recurring", "program")
    if t and t not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of: {', '.join(allowed)}",
        )
    rows = _combined_read_rows(t or None, src or None)
    if wd:
        wdl = wd.lower()
        rows = [
            r
            for r in rows
            if isinstance(r.get("weekday"), str) and r.get("weekday", "").strip().lower() == wdl
        ]
    return finalize_api_list(rows, expand)[:limit]


@app.get("/search", response_model=SearchResponse)
def search_items(
    q: str = Query(..., min_length=1, description="Substring match on title (case-insensitive)"),
    item_type: str | None = Query(None, alias="type", description="Limit to event | recurring | program"),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(LIMIT_DEFAULT, ge=LIMIT_MIN, le=LIMIT_MAX),
    expand: bool = Query(False, description="Return full payloads if true"),
) -> SearchResponse:
    query_lower = q.strip().lower()
    if not query_lower:
        raise HTTPException(status_code=400, detail="q must not be empty")
    t = item_type.strip() if item_type else None
    src = source.strip() if source else None
    allowed = ("event", "recurring", "program")
    if t and t not in allowed:
        raise HTTPException(status_code=400, detail=f"type must be one of: {', '.join(allowed)}")
    try:
        rows = _combined_read_rows(t or None, src or None)
        if not isinstance(rows, list):
            rows = []
        intent = parse_intent(q)
        if should_expand(intent, q):
            expanded_queries = expand_query(q)
        else:
            expanded_queries = [q.strip()]
        if not isinstance(expanded_queries, list) or not expanded_queries:
            expanded_queries = [q.strip()]
        matched = match_rows_for_queries(rows, expanded_queries)
        if not isinstance(matched, list):
            matched = []
        if not matched:
            matched = get_fallback_rows()
        results = rank_search_results(matched, q, intent, expand, limit)
        if not isinstance(results, list):
            results = []
        ai_payload: SearchAISection | None = None
        if should_use_ai(results, intent):
            raw = generate_suggestions(q, intent, results)
            sugs = raw.get("suggestions") if isinstance(raw, dict) else None
            ai_payload = SearchAISection(suggestions=_sanitize_ai_suggestions(sugs))
        if os.getenv("DEBUG_SEARCH", "").strip() == "1":
            print("QUERY:", q)
            print("INTENT:", intent)
            print("EXPANDED:", expanded_queries)
            print("TOP 3:", [r.get("title") for r in results[:3]])
        return SearchResponse(results=results, ai=ai_payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("search failed: %s", exc)
        return SearchResponse(
            results=[],
            ai=SearchAISection(suggestions=fallback_generic_suggestions()),
        )


@app.get("/discover", response_model=DiscoverResponse)
def discover() -> DiscoverResponse:
    rows = _combined_read_rows(None, None) + list_expanded_slot_payloads()
    rows = rows if isinstance(rows, list) else []
    normalized = finalize_api_list(rows, False)
    today_rows = get_today(normalized)
    weekend_rows = get_weekend(normalized)
    popular_rows = get_popular(normalized)
    return DiscoverResponse(today=today_rows, weekend=weekend_rows, popular=popular_rows)


def _build_debug_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:5]:
        rid = str(row.get("id") or "").strip()
        if not rid:
            continue
        out.append(
            {
                "id": rid,
                "final_score": float(row.get("score") or 0.0),
                "components": row.get("_score_components") or {},
            }
        )
    return out


@app.post("/ai/recommend")
def ai_recommend(body: AIRecommendRequest, debug: bool = Query(False)) -> list[AIRecommendation] | dict[str, Any]:
    query = body.query.strip()
    real_events = _events_for_ai_context(limit=150)
    seed_events = _load_seed_events() if ENABLE_SEED_DATA else []
    events = real_events + seed_events
    events, filter_stats = _filter_stale_ai_events(events)
    filter_stats["seed_event_count"] = len(seed_events)
    filter_stats["real_event_count"] = len(real_events)
    payload = _format_for_ai(events)
    if not payload:
        return []
    start_lookup = {str(e.get("id") or "").strip(): str(e.get("start") or "") for e in payload}
    event_text_lookup = {
        str(e.get("id") or "").strip(): build_event_embedding_text(e)
        for e in payload
        if str(e.get("id") or "").strip()
    }
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()

    # Local deterministic fallback always available.
    fallback_ranked = _local_ai_rank(query, payload)
    fallback_ranked = apply_weighted_rank_boosts(
        query,
        fallback_ranked,
        start_lookup=start_lookup,
        event_text_lookup=event_text_lookup,
    )
    fallback_ranked.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    fallback_ranked = fallback_ranked[:5]

    if not has_openai_key() or OpenAI is None:
        final = [AIRecommendation(id=str(r.get("id") or ""), score=float(r.get("score") or 0.0), reason=str(r.get("reason") or "Relevant match")) for r in fallback_ranked if str(r.get("id") or "").strip()]
        try:
            log_ai_interaction(query, [x.id for x in final])
        except Exception:
            pass
        if debug:
            return {
                "results": [x.model_dump() for x in final],
                "breakdown": _build_debug_breakdown(fallback_ranked),
                "weights": WEIGHTS,
                "eligibility": filter_stats,
            }
        return final

    try:
        client = OpenAI(api_key=api_key)
        prompt = (
            "You are a recommendation engine.\n"
            f"User query: {query}\n"
            f"Events: {json.dumps(payload, ensure_ascii=True)}\n\n"
            "Return ONLY a JSON array of up to 5 objects with keys:\n"
            "id (string), score (0..1 float), reason (short string).\n"
            "Only use IDs that exist in the provided events."
        )
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        parsed = _parse_ai_response_json(text)
        allowed_ids = {str(e["id"]) for e in payload if str(e.get("id") or "").strip()}
        clean: list[AIRecommendation] = []
        for r in parsed:
            rid = str(r.get("id") or "").strip()
            if not rid or rid not in allowed_ids:
                continue
            try:
                score = float(r.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            reason = str(r.get("reason") or "Relevant match").strip() or "Relevant match"
            clean.append(AIRecommendation(id=rid, score=max(0.0, min(1.0, score)), reason=reason))
        if clean:
            boosted_input = [{"id": x.id, "score": x.score, "reason": x.reason} for x in clean]
            boosted = apply_weighted_rank_boosts(
                query,
                boosted_input,
                start_lookup=start_lookup,
                event_text_lookup=event_text_lookup,
            )
            boosted.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
            final = [
                AIRecommendation(
                    id=str(r.get("id") or ""),
                    score=float(r.get("score") or 0.0),
                    reason=str(r.get("reason") or "Relevant match"),
                )
                for r in boosted[:5]
                if str(r.get("id") or "").strip()
            ]
            if final:
                try:
                    log_ai_interaction(query, [x.id for x in final])
                except Exception:
                    pass
                if debug:
                    return {
                        "results": [x.model_dump() for x in final],
                        "breakdown": _build_debug_breakdown(boosted),
                        "weights": WEIGHTS,
                        "eligibility": filter_stats,
                    }
                return final
    except Exception as exc:
        logger.warning("ai_recommend fallback due to error: %s", exc)

    final = [
        AIRecommendation(
            id=str(r.get("id") or ""),
            score=float(r.get("score") or 0.0),
            reason=str(r.get("reason") or "Relevant match"),
        )
        for r in fallback_ranked
        if str(r.get("id") or "").strip()
    ]
    try:
        log_ai_interaction(query, [x.id for x in final])
    except Exception:
        pass
    if debug:
        return {
            "results": [x.model_dump() for x in final],
            "breakdown": _build_debug_breakdown(fallback_ranked),
            "weights": WEIGHTS,
            "eligibility": filter_stats,
        }
    return final


@app.post("/ai/click")
def ai_click(body: AIClickRequest) -> dict[str, bool]:
    try:
        record_ai_click(body.query, body.clicked_id)
    except Exception:
        pass
    return {"success": True}


@app.get("/debug/ai-status")
def debug_ai_status() -> dict[str, Any]:
    has_key = has_openai_key() and OpenAI is not None
    embeddings_active = False
    reason = "missing_openai_key_or_package"
    if has_key:
        reason = _embedding_debug_reason()
        embeddings_active = reason == "ok"
    query_cache_count = sum(1 for k in _embedding_cache if k.startswith("q:"))
    event_cache_count = sum(1 for k in _embedding_cache if k.startswith("e:"))
    return {
        "has_key": has_key,
        "embeddings_active": embeddings_active,
        "reason": reason,
        "cache_size": len(_embedding_cache),
        "query_cache_count": query_cache_count,
        "event_cache_count": event_cache_count,
    }


@app.get("/debug/ai-weight-check")
def debug_ai_weight_check() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for query in TEST_QUERIES:
        payload = ai_recommend(AIRecommendRequest(query=query), debug=True)
        results[query] = payload
    return {"weights": WEIGHTS, "queries": TEST_QUERIES, "results": results}


@app.post("/submit", response_model=SubmitResponse)
def submit_item(body: SubmitRequest) -> SubmitResponse:
    title = body.title.strip()
    start_date = (body.start_date or "").strip()
    location = (body.location or "").strip()
    if not title or not start_date or not location:
        return JSONResponse(status_code=400, content={"error": "invalid_submission"})
    if _is_junk_title(title):
        return JSONResponse(status_code=400, content={"error": "invalid_submission"})
    category = body.category.strip().lower()
    if category not in ("event", "service"):
        raise HTTPException(status_code=400, detail="category must be event or service")
    if "havasu" not in location.lower():
        raise HTTPException(status_code=400, detail="Only Lake Havasu submissions are allowed")
    dup_id = find_duplicate_submission_id(
        normalized_title=" ".join(title.lower().split()),
        start_date=start_date,
    )
    if dup_id:
        return SubmitResponse(success=True, id=dup_id, duplicate=True)
    sid = create_submission(
        title=title,
        description=(body.description or "").strip(),
        tags=_normalize_submit_tags(body.tags),
        category=category,
        start_date=start_date,
        location=location,
    )
    return SubmitResponse(success=True, id=sid)


@app.post("/submit-activity", response_model=SubmitResponse)
def submit_activity(body: SubmitActivityRequest) -> SubmitResponse:
    title = body.title.strip()
    location = body.location.strip()
    if not title or not location or not body.time_slots:
        return JSONResponse(status_code=400, content={"error": "invalid_submission"})
    if _is_junk_title(title):
        return JSONResponse(status_code=400, content={"error": "invalid_submission"})
    if "havasu" not in location.lower():
        raise HTTPException(status_code=400, detail="Only Lake Havasu submissions are allowed")

    slots: list[SlotInput] = []
    for slot in body.time_slots:
        slots.append(
            SlotInput(
                start_time=slot.start_time.strip(),
                end_time=slot.end_time.strip(),
                day_of_week=slot.day_of_week,
                date=(slot.date or "").strip() or None,
                recurring=bool(slot.recurring),
            )
        )

    activity_id = ingest_activity(
        ActivityInput(
            title=title,
            location=location,
            activity_type="schedule",
            category=body.category.strip().lower() or "events",
            tags=_normalize_submit_tags(body.tags),
            time_slots=slots,
            source="user",
            status="pending",
            description=(body.description or "").strip(),
        )
    )
    return SubmitResponse(success=True, id=activity_id)


@app.get("/admin/pending")
def admin_pending_submissions() -> list[dict[str, Any]]:
    return list_pending_submissions() + list_pending_activities()


@app.get("/admin/submissions")
def admin_list_submissions(status: str = Query("pending")) -> list[dict[str, Any]]:
    s = status.strip().lower()
    if s not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be pending|approved|rejected")
    if s == "pending":
        return list_submissions("pending")
    if s == "approved":
        return list_submissions("approved")
    return list_submissions("rejected")


@app.post("/admin/approve")
def admin_approve_submission(id: str = Query(..., min_length=1)) -> dict[str, bool]:
    if id.startswith("a-"):
        ok = set_activity_status(id, "approved")
        if not ok:
            raise HTTPException(status_code=404, detail="Activity not found")
        return {"success": True}
    ok = update_submission_status(id, "approved")
    if not ok:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"success": True}


@app.post("/admin/reject")
def admin_reject_submission(id: str = Query(..., min_length=1)) -> dict[str, bool]:
    if id.startswith("a-"):
        ok = delete_activity(id) or set_activity_status(id, "rejected")
        if not ok:
            raise HTTPException(status_code=404, detail="Activity not found")
        return {"success": True}
    # Keep rejected rows out of pending/live; remove to keep table clean.
    ok = delete_submission(id) or update_submission_status(id, "rejected")
    if not ok:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"success": True}


@app.post("/admin/feature")
def admin_feature_submission(
    id: str = Query(..., min_length=1),
    days: int = Query(7, ge=1, le=90),
) -> dict[str, bool]:
    ok = set_submission_featured(id, days=days)
    if not ok:
        raise HTTPException(status_code=404, detail="Approved submission not found")
    return {"success": True}


@app.post("/admin/unfeature")
def admin_unfeature_submission(id: str = Query(..., min_length=1)) -> dict[str, bool]:
    ok = clear_submission_featured(id)
    if not ok:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"success": True}


@app.post("/track/view")
def track_view(body: TrackRequest, request: Request) -> dict[str, bool]:
    # Silent no-op for unknown IDs to avoid breaking UI flows.
    try:
        sid = body.id.strip()
        if sid and _tracking_should_increment(action="view", submission_id=sid, request=request):
            ok = increment_submission_view(sid)
            if not ok:
                increment_activity_view(sid)
    except Exception:
        pass
    return {"success": True}


@app.post("/track/click")
def track_click(body: TrackRequest, request: Request) -> dict[str, bool]:
    # Silent no-op for unknown IDs to avoid breaking UI flows.
    try:
        sid = body.id.strip()
        if sid and _tracking_should_increment(action="click", submission_id=sid, request=request):
            ok = increment_submission_click(sid)
            if not ok:
                increment_activity_click(sid)
    except Exception:
        pass
    return {"success": True}


@app.get("/notifications/feed", response_model=NotificationFeedResponse)
def notifications_feed(limit: int = Query(20, ge=1, le=50)) -> NotificationFeedResponse:
    try:
        items = list_notifications_feed(limit=limit)
    except Exception:
        items = []
    return NotificationFeedResponse(items=items)


@app.get("/today")
def get_today_view(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> dict:
    """Calendar events on today's date + recurring rows for today's weekday."""
    today = date.today()
    today_iso = today.isoformat()
    today_name = today.strftime("%A")

    events_raw: list[dict] = []
    for e in _all_calendar_event_payloads():
        if not include_in_homepage_calendar_lists(e):
            continue
        start, end = _event_date_span(e)
        if start is None:
            continue
        if end is None:
            end = start
        if start <= today <= end:
            events_raw.append(e)

    recurring_raw: list[dict] = []
    for row in list_items(item_type="recurring"):
        w = row.get("weekday")
        if not isinstance(w, str) or not w.strip():
            continue
        if w.strip().lower() != today_name.lower():
            continue
        recurring_raw.append(row)

    events_norm = finalize_api_list(events_raw, expand)
    events_norm.sort(key=homepage_calendar_sort_key)
    recurring_norm = finalize_api_list(recurring_raw, expand)
    recurring_norm.sort(key=homepage_calendar_sort_key)

    return {
        "date": today_iso,
        "weekday": today_name,
        "events": events_norm,
        "recurring": recurring_norm,
    }


@app.get("/week")
def get_week_view(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> dict:
    """Events with start_date in the next 7 days (inclusive) + all recurring grouped by weekday."""
    today = date.today()
    end = today + timedelta(days=7)

    events_raw: list[dict] = []
    for e in _all_calendar_event_payloads():
        if not include_in_homepage_calendar_lists(e):
            continue
        start, _ = _event_date_span(e)
        if start is None:
            continue
        if today.isoformat() <= start.isoformat() <= end.isoformat():
            events_raw.append(e)

    recurring_all = list_items(item_type="recurring")
    by_wd: dict[str, list[dict]] = defaultdict(list)
    for r in recurring_all:
        w = r.get("weekday")
        if not isinstance(w, str) or not w.strip():
            continue
        key = w.strip().title()
        by_wd[key].append(r)
    ordered = sorted(by_wd.keys(), key=lambda n: _WEEKDAY_ORDER.get(n.lower(), 99))
    recurring_by_weekday = {wd: by_wd[wd] for wd in ordered}

    events_norm = finalize_api_list(events_raw, expand)
    events_norm.sort(key=homepage_calendar_sort_key)
    recurring_sorted = {
        wd: sorted(
            finalize_api_list(recurring_by_weekday[wd], expand),
            key=homepage_calendar_sort_key,
        )
        for wd in ordered
    }

    return {
        "start": today.isoformat(),
        "end": end.isoformat(),
        "events": events_norm,
        "recurring_by_weekday": recurring_sorted,
    }


@app.get("/public/event/{event_ref}")
def get_public_event_by_ref(event_ref: str) -> dict:
    """
    Stable public detail: `u-{user_events.id}` for business-submitted events,
    `c-{items.id}` for crawler/stored items. Returns merged payload (expand=true)
    so venue/address/description are available for the UI.
    """
    if not re.fullmatch(r"[uc]-[0-9]+", event_ref):
        raise HTTPException(status_code=400, detail="Invalid event reference")
    kind, _, digits = event_ref.partition("-")
    num = int(digits)
    if kind == "u":
        row = get_user_event_with_profile_fields(num)
        if row is None:
            raise HTTPException(status_code=404, detail="Event not found")
        biz = get_business_by_id(int(row["business_id"]))
        if (
            biz is None
            or str(biz.get("role")) != "business"
            or str(biz.get("status")) != "approved"
        ):
            raise HTTPException(status_code=404, detail="Event not found")
        raw = map_user_event_row_to_item_payload(dict(row))
    else:
        raw = get_item_payload_by_id(num)
        if raw is None:
            raise HTTPException(status_code=404, detail="Event not found")
    out = finalize_api_list([raw], True)
    return out[0]


@app.get("/schedule/today")
def get_schedule_today(
    expand: bool = Query(False, description="Return full payloads in items if true"),
) -> dict:
    """Today's recurring schedule: sorted and grouped by start_time."""
    today = date.today()
    today_name = today.strftime("%A").lower()
    rows: list[dict] = []
    for row in list_items(item_type="recurring"):
        w = row.get("weekday")
        if not isinstance(w, str) or not w.strip():
            continue
        if w.strip().lower() != today_name:
            continue
        rows.append(row)

    finalized = finalize_api_list(rows, expand)
    if expand:
        by_time: dict[str, list[dict]] = defaultdict(list)
        for r in finalized:
            st_key = coalesce_str(r.get("start_time"))
            by_time[st_key].append(r)
        sorted_times = sorted(
            by_time.keys(),
            key=lambda k: time_sort_value(k) if k else MISSING_TIME_SORT,
        )
        grouped = [{"start_time": t or "", "items": by_time[t]} for t in sorted_times]
        return {
            "weekday": today.strftime("%A"),
            "items": finalized,
            "by_start_time": {t or "": by_time[t] for t in sorted_times},
            "groups": grouped,
        }
    norm = finalized
    by_norm: dict[str, list[dict]] = defaultdict(list)
    for n in norm:
        st_key = n.get("start_time") or ""
        by_norm[st_key].append(n)
    sorted_t = sorted(
        by_norm.keys(),
        key=lambda k: time_sort_value(k) if k else MISSING_TIME_SORT,
    )
    grouped_n = [{"start_time": t, "items": by_norm[t]} for t in sorted_t]
    return {
        "weekday": today.strftime("%A"),
        "items": norm,
        "by_start_time": {t: by_norm[t] for t in sorted_t},
        "groups": grouped_n,
    }


@app.get("/schedule/week")
def get_schedule_week(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> dict:
    """All recurring items grouped by weekday (Monday-first)."""
    recurring = list_items(item_type="recurring")
    by_wd: dict[str, list[dict]] = defaultdict(list)
    for r in recurring:
        w = r.get("weekday")
        if not isinstance(w, str) or not w.strip():
            continue
        key = w.strip().title()
        by_wd[key].append(r)
    ordered = sorted(by_wd.keys(), key=lambda n: _WEEKDAY_ORDER.get(n.lower(), 99))
    return {
        "by_weekday": {
            wd: finalize_api_list(by_wd[wd], expand) for wd in ordered
        }
    }


@app.get("/events")
def get_events(
    source: str | None = Query(None, description="Filter by crawler source"),
    expand: bool = Query(False, description="Return full payloads if true"),
) -> list[dict]:
    src = source.strip() if source else None
    if src == "user":
        return finalize_api_list(list_user_event_payloads_for_public(), expand)
    rows = list_events(source=src or None)
    if src:
        return finalize_api_list(rows, expand)
    return finalize_api_list(rows + list_user_event_payloads_for_public(), expand)


@app.get("/home")
def get_home() -> dict:
    items = finalize_api_list(_upcoming_event_payloads(), False)[:_HOME_EVENTS_LIMIT]
    return {
        "sections": [
            {
                "type": "events",
                "title": "What's Happening",
                "items": items,
            }
        ]
    }


@app.get("/events/upcoming")
def get_events_upcoming(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> list[dict]:
    return finalize_api_list(_upcoming_event_payloads(), expand)


@app.get("/events/today")
def get_events_today(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> list[dict]:
    today = date.today()
    out: list[dict] = []
    for e in _all_events():
        start, end = _event_date_span(e)
        if start is None or end is None:
            continue
        if start <= today <= end:
            out.append(e)
    return finalize_api_list(out, expand)


@app.get("/events/weekend")
def get_events_weekend(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> list[dict]:
    today = date.today()
    fri, sun = _upcoming_weekend_bounds(today)
    picked: list[dict] = []
    for e in _all_events():
        start, end = _event_date_span(e)
        if start is None or end is None:
            continue
        if end < fri or start > sun:
            continue
        picked.append(e)
    return finalize_api_list(picked, expand)


@app.get("/events/with-location")
def get_events_with_location(
    expand: bool = Query(False, description="Return full payloads if true"),
) -> list[dict]:
    rows = [e for e in _all_events() if e.get("has_location") is True]
    return finalize_api_list(rows, expand)


@app.get("/events/sources")
def get_event_sources_summary() -> dict[str, int]:
    return count_events_by_source()


@app.get("/events/summary")
def get_events_summary() -> dict:
    events = _all_events()
    total = len(events)
    with_dates = sum(1 for e in events if _parse_iso_date(e.get("start_date")) is not None)
    with_location = sum(1 for e in events if e.get("has_location") is True)
    with_time = sum(1 for e in events if e.get("has_time") is True)
    return {
        "total": total,
        "with_dates": with_dates,
        "with_location": with_location,
        "with_time": with_time,
    }

