from __future__ import annotations

import logging
import os
from typing import Any

from core.tags import infer_tags
from core.trust_score import compute_trust_score

logger = logging.getLogger(__name__)

# Lexicographic time sort: real HH:MM first; missing / empty sorts last.
MISSING_TIME_SORT = "99:99"

_STRING_FIELDS_EXPAND = frozenset(
    {
        "title",
        "weekday",
        "start_time",
        "end_time",
        "location_label",
        "source",
        "source_url",
        "start_date",
        "end_date",
        "date_text",
        "description",
        "short_description",
        "venue_name",
        "address",
    }
)

# Always present for expand=true (frontend-safe minimum).
_GUARANTEED_EXPAND_KEYS = ("title", "start_date", "source")


def _s(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


def coalesce_str(val: Any) -> str:
    """None and blanks -> '' (API buckets / display)."""
    return _s(val)


def time_sort_value(val: Any) -> str:
    """Sort key for times: present HH:MM first; missing last."""
    s = _s(val)
    return s if s else MISSING_TIME_SORT


def _effective_location_label(payload: dict[str, Any]) -> str:
    loc = _s(payload.get("location_label"))
    if loc:
        return loc
    vn = _s(payload.get("venue_name"))
    ad = _s(payload.get("address"))
    if vn and ad:
        return f"{vn}, {ad}"
    return vn or ad


def _location_any_raw(payload: dict[str, Any]) -> bool:
    """True if any of label / venue / address has non-empty content (after strip)."""
    return bool(
        _s(payload.get("location_label"))
        or _s(payload.get("venue_name"))
        or _s(payload.get("address"))
    )


def _best_description(payload: dict[str, Any]) -> str:
    d = _s(payload.get("description"))
    s = _s(payload.get("short_description"))
    if not d:
        return s
    if not s:
        return d
    return d if len(d) >= len(s) else s


def _source_urls_list(payload: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    raw = payload.get("source_urls")
    if isinstance(raw, list):
        for u in raw:
            if isinstance(u, str) and u.strip() and u.strip() not in seen:
                seen.add(u.strip())
                out.append(u.strip())
    su = _s(payload.get("source_url"))
    if su and su not in seen:
        out.append(su)
    return out


def normalized_sort_tuple(n: dict[str, Any]) -> tuple[str, str, str]:
    """Single sort rule for API lists: (start_date, start_time, title)."""
    return (
        n.get("start_date") or "",
        time_sort_value(n.get("start_time")),
        (n.get("title") or "").lower(),
    )


def homepage_calendar_sort_key(n: dict[str, Any]) -> tuple[str, int, float, str]:
    """Sort for /today and /week: time, then user events first, then trust, then title."""
    tm = time_sort_value(n.get("start_time"))
    user_first = 0 if str(n.get("source") or "").lower() == "user" else 1
    try:
        tr = float(n.get("trust_score"))
    except (TypeError, ValueError):
        tr = 0.0
    return (tm, user_first, -tr, (n.get("title") or "").lower())


def normalize_item(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Single frontend-friendly shape for any stored item (from payload_json).
    String fields are never null — use "".
    """
    typ = payload.get("type") or "event"
    if typ not in ("event", "recurring", "program"):
        typ = str(typ)

    start_time = _s(payload.get("start_time"))
    end_time = _s(payload.get("end_time"))
    location_display = _effective_location_label(payload)

    out: dict[str, Any] = {
        "title": _s(payload.get("title")),
        "type": typ,
        "start_date": _s(payload.get("start_date")),
        "end_date": _s(payload.get("end_date")),
        "weekday": _s(payload.get("weekday")),
        "start_time": start_time,
        "end_time": end_time,
        "location_label": location_display,
        "source": _s(payload.get("source")),
        "source_url": _s(payload.get("source_url")),
        "source_urls": _source_urls_list(payload),
        "description": _best_description(payload),
        "has_start_time": bool(start_time),
        "has_end_time": bool(end_time),
        "has_location": _location_any_raw(payload),
    }
    if _s(payload.get("source")) == "user":
        bid = payload.get("business_id")
        if bid is not None:
            try:
                out["business_id"] = int(bid)
            except (TypeError, ValueError):
                pass
        bn = _s(payload.get("business_name"))
        if bn:
            out["business_name"] = bn
        bc = _s(payload.get("business_category"))
        if bc:
            out["business_category"] = bc
    uid = payload.get("user_event_id")
    iid = payload.get("item_db_id")
    activity_id = payload.get("activity_id")
    if uid is not None:
        try:
            out["event_ref"] = f"u-{int(uid)}"
        except (TypeError, ValueError):
            pass
    elif activity_id is not None:
        aid = _s(activity_id)
        if aid:
            out["event_ref"] = aid
    elif iid is not None:
        try:
            out["event_ref"] = f"c-{int(iid)}"
        except (TypeError, ValueError):
            pass
    if os.environ.get("HAVASU_API_DEBUG_SOURCE") == "1":
        out["debug_source_type"] = "user" if _s(payload.get("source")) == "user" else "crawler"
    aid = _s(activity_id)
    if aid:
        out["activity_id"] = aid
    if typ == "event":
        out["date"] = out["start_date"]
    else:
        out["date"] = ""

    desc_for_tags = _best_description(payload) or ""
    raw_tags = payload.get("tags")
    merged_tags: list[str] = []
    if isinstance(raw_tags, list):
        merged_tags = [str(x).strip() for x in raw_tags if str(x).strip()]
    for t in infer_tags(_s(payload.get("title")), desc_for_tags):
        if t not in merged_tags:
            merged_tags.append(t)
    merged_tags.sort()
    out["tags"] = merged_tags

    cat = payload.get("category")
    out["category"] = _s(cat) if cat is not None else ""

    if _s(payload.get("source")) == "user":
        out["trust_score"] = 1.0
    else:
        out["trust_score"] = float(compute_trust_score(payload))
    out["location"] = location_display
    out["id"] = out.get("event_ref") or ""
    out["is_featured"] = bool(payload.get("is_featured"))
    out["featured_until"] = _s(payload.get("featured_until"))
    try:
        out["view_count"] = int(payload.get("view_count") or 0)
    except (TypeError, ValueError):
        out["view_count"] = 0
    try:
        out["click_count"] = int(payload.get("click_count") or 0)
    except (TypeError, ValueError):
        out["click_count"] = 0

    return out


def normalize_items(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_item(p) for p in payloads]


def sort_normalized_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort already-normalized rows (same key as finalize_api_list)."""
    return sorted(items, key=normalized_sort_tuple)


def sanitize_payload_for_expand(p: dict[str, Any]) -> dict[str, Any]:
    """Coerce None -> ''; guarantee title, start_date, source for expand responses."""
    out = dict(p)
    for k in _STRING_FIELDS_EXPAND:
        if k in out and out[k] is None:
            out[k] = ""
    for k in _GUARANTEED_EXPAND_KEYS:
        if k not in out or out[k] is None:
            out[k] = ""
        elif not isinstance(out[k], str):
            out[k] = str(out[k]).strip()
    return out


def expand_merged(raw: dict[str, Any], norm: dict[str, Any]) -> dict[str, Any]:
    """Raw crawler row overlaid with normalized core fields, then sanitized."""
    merged = dict(raw)
    for k, v in norm.items():
        merged[k] = v
    return sanitize_payload_for_expand(merged)


def _verify_sort_order(items: list[dict[str, Any]]) -> None:
    """Dev-only: set HAVASU_API_VERIFY_SORT=1 to log if order breaks."""
    if os.environ.get("HAVASU_API_VERIFY_SORT") != "1":
        return
    if len(items) < 2:
        return
    norms = [normalize_item(x) for x in items]
    tups = [normalized_sort_tuple(n) for n in norms]
    if tups != sorted(tups):
        logger.warning(
            "HAVASU_API_VERIFY_SORT: list not ordered by (start_date, start_time, title); sample=%s",
            tups[:8],
        )


def finalize_api_list(raw_rows: list[dict[str, Any]], expand: bool) -> list[dict[str, Any]]:
    """
    Single API pipeline: raw DB payloads → normalize → sort → return normalized
    or expand (merged raw+norm, guaranteed keys).
    """
    if not raw_rows:
        return []
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (r, normalize_item(r)) for r in raw_rows
    ]
    pairs.sort(key=lambda p: normalized_sort_tuple(p[1]))
    if expand:
        out = [expand_merged(raw, norm) for raw, norm in pairs]
    else:
        out = [norm for _, norm in pairs]
    _verify_sort_order(out)
    return out
