from __future__ import annotations

from typing import Any

from core.models import validate_item_payload


def normalize_schedule_item(parsed: dict[str, Any], *, source: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": source,
        "type": "recurring",
        "title": parsed.get("title"),
        "start_date": None,
        "end_date": None,
        "date_text": None,
        "start_time": parsed.get("start_time"),
        "end_time": parsed.get("end_time"),
        "has_time": parsed.get("has_time", False),
        "has_location": bool(parsed.get("location_label")),
        "venue_name": None,
        "address": None,
        "description": parsed.get("description"),
        "short_description": None,
        "source_url": parsed.get("source_url"),
        "weekday": parsed.get("weekday"),
        "location_label": parsed.get("location_label"),
    }
    return validate_item_payload(payload)


def normalize_program_item(parsed: dict[str, Any], *, source: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": source,
        "type": "program",
        "title": parsed.get("title"),
        "start_date": None,
        "end_date": None,
        "date_text": None,
        "start_time": None,
        "end_time": None,
        "has_time": False,
        "has_location": bool(parsed.get("location_label")),
        "venue_name": None,
        "address": None,
        "description": parsed.get("description"),
        "short_description": None,
        "source_url": parsed.get("source_url"),
        "weekday": None,
        "location_label": parsed.get("location_label"),
        "external_url": parsed.get("external_url"),
    }
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("program item requires non-empty title")
    return validate_item_payload(payload)
