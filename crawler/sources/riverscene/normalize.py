from __future__ import annotations

import re
from datetime import date
from typing import Any

from dateutil import parser as date_parser

from core.models import validate_event_payload


def _safe_parse_date(value: str) -> date | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def _parse_date_range_from_headline(date_raw: str | None) -> tuple[str | None, str | None]:
    if not date_raw:
        return None, None
    raw = date_raw.strip()

    range_match = re.search(
        r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),\s*(\d{4})",
        raw,
    )
    if range_match:
        month, start_day, end_day, year = range_match.groups()
        start = _safe_parse_date(f"{month} {start_day}, {year}")
        end = _safe_parse_date(f"{month} {end_day}, {year}")
        if start and end:
            return start.isoformat(), end.isoformat()

    single = _safe_parse_date(raw)
    if single:
        iso = single.isoformat()
        return iso, iso

    return None, None


def _coerce_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def normalize_event(parsed: dict[str, Any], *, source: str) -> dict[str, Any]:
    start_date = _coerce_date(parsed.get("start_date"))
    end_date = _coerce_date(parsed.get("end_date"))

    if start_date is None and end_date is None:
        start_date, end_date = _parse_date_range_from_headline(parsed.get("date_raw"))

    start_time = parsed.get("start_time")
    end_time = parsed.get("end_time")
    if isinstance(start_time, str) and not start_time.strip():
        start_time = None
    if isinstance(end_time, str) and not end_time.strip():
        end_time = None

    def _opt_str(key: str) -> str | None:
        val = parsed.get(key)
        if val is None:
            return None
        if isinstance(val, str):
            stripped = val.strip()
            return stripped or None
        return None

    title = _opt_str("title")
    venue_name = _opt_str("venue_name")
    address = _opt_str("address")
    description = _opt_str("description")
    short_description = _opt_str("short_description")
    date_text = _opt_str("date_text")
    if date_text is None:
        date_text = _opt_str("date_raw")

    has_time = start_time is not None
    has_location = bool(venue_name or address)

    source_url = parsed.get("source_url")
    if isinstance(source_url, str):
        source_url = source_url.strip() or None

    payload: dict[str, Any] = {
        "source": source,
        "type": "event",
        "title": title,
        "start_date": start_date,
        "end_date": end_date,
        "date_text": date_text,
        "start_time": start_time,
        "end_time": end_time,
        "has_time": has_time,
        "has_location": has_location,
        "venue_name": venue_name,
        "address": address,
        "description": description,
        "short_description": short_description,
        "source_url": source_url,
    }
    for meta_k in ("riverscene_date_source", "riverscene_date_confidence"):
        v = parsed.get(meta_k)
        if isinstance(v, str) and v.strip():
            payload[meta_k] = v.strip()
    return validate_event_payload(payload)
