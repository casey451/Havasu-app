from __future__ import annotations

from typing import Any


def normalize_event_title_key(title: Any) -> str:
    if not isinstance(title, str):
        return ""
    return title.strip().lower()


def normalize_event_date_key(start_date: Any) -> str:
    """ISO date prefix YYYY-MM-DD for stable keys and SQL joins."""
    if start_date is None:
        return ""
    s = str(start_date).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


def compute_item_key(payload: dict[str, Any]) -> str:
    """
    Stable logical identity for dedupe (stored in DB, computed at upsert).

    * **event** — ``{source}|event|{title}|{start_date}`` (title lowercased, date YYYY-MM-DD).
    * **recurring** — ``{source}|recurring|{title}|{weekday}|{start_time}|{end_time}``.
    """
    source = (payload.get("source") or "").strip()
    typ = (payload.get("type") or "").strip()
    title = (payload.get("title") or "").strip()
    weekday = (payload.get("weekday") or "").strip()
    st = (payload.get("start_time") or "").strip()
    et = (payload.get("end_time") or "").strip()
    sd = (payload.get("start_date") or "").strip()
    loc = (payload.get("location_label") or "").strip()

    if typ == "event":
        tk = normalize_event_title_key(payload.get("title"))
        sdk = normalize_event_date_key(payload.get("start_date"))
        return f"{source}|event|{tk}|{sdk}"
    if typ == "program":
        ext = (payload.get("external_url") or "").strip()
        su = (payload.get("source_url") or "").strip()
        anchor = ext if ext else su
        return f"{source}|program|{title}|{anchor}"
    if typ == "recurring":
        return f"{source}|recurring|{title}|{weekday}|{st}|{et}"
    return f"{source}|{typ}|{title}|{weekday}|{st}|{et}|{sd}|{loc}"
