from __future__ import annotations

import json
from typing import Any


def map_user_event_row_to_item_payload(row: dict[str, Any]) -> dict[str, Any]:
    """
    Shape compatible with `normalize_item` / crawler `items.payload_json` for events.
    User-submitted rows use source=\"user\".
    """
    sd = str(row.get("start_date") or "").strip()
    if len(sd) >= 10 and sd[4] == "-" and sd[7] == "-":
        sd = sd[:10]
    desc = row.get("description")
    desc_s = desc.strip() if isinstance(desc, str) else ""
    st = (row.get("start_time") or "").strip() if row.get("start_time") else ""
    et = (row.get("end_time") or "").strip() if row.get("end_time") else ""
    loc = (row.get("location_label") or "").strip() if row.get("location_label") else ""
    vn = str(row.get("venue_name") or "").strip()
    ad = str(row.get("address") or "").strip()

    raw_tags = row.get("tags")
    tags_list: list[str] = []
    if isinstance(raw_tags, str) and raw_tags.strip():
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                tags_list = [str(x).strip() for x in parsed if str(x).strip()]
        except (json.JSONDecodeError, TypeError):
            tags_list = []

    cat = str(row.get("category") or "").strip()

    out: dict[str, Any] = {
        "title": str(row.get("title") or "").strip(),
        "type": "event",
        "start_date": sd,
        "end_date": sd,
        "weekday": "",
        "start_time": st,
        "end_time": et,
        "location_label": loc,
        "venue_name": vn or None,
        "address": ad or None,
        "description": desc_s if desc_s else None,
        "short_description": (desc_s[:280] if desc_s else None),
        "source": "user",
        "source_url": "",
        "business_id": int(row["business_id"]),
        "user_event_id": int(row["id"]),
        "has_time": bool(st),
        "has_location": bool(loc or vn or ad),
        "tags": tags_list,
        "category": cat or None,
        # Business-submitted: fixed trust; normalize_item honors this for source=user.
        "trust_score": 1.0,
    }
    bp_name = row.get("bp_name")
    if isinstance(bp_name, str) and bp_name.strip():
        out["business_name"] = bp_name.strip()
    bp_cat = row.get("bp_category_group")
    if isinstance(bp_cat, str) and bp_cat.strip():
        out["business_category"] = bp_cat.strip()
    return out
