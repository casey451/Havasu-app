from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_PATH_JSON = Path(__file__).resolve().parents[1] / "data" / "havasu_100_businesses.json"
DATA_PATH_TXT = Path(__file__).resolve().parents[1] / "data" / "havasu_100_businesses.txt"


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        s = str(raw).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def load_businesses(
    *,
    file_path: str | Path | None = None,
    existing_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Load real business records as event-like rows without mutating DB.

    Returns:
      (loaded_rows, stats)
    """
    if file_path is not None:
        path = Path(file_path)
    elif DATA_PATH_JSON.exists():
        path = DATA_PATH_JSON
    else:
        path = DATA_PATH_TXT
    stats = {
        "total_read": 0,
        "inserted_count": 0,
        "skipped_count": 0,
        "duplicates_skipped": 0,
        "missing_required_skipped": 0,
    }

    if not path.exists():
        print(f"[load_businesses] file not found: {path}")
        return [], stats

    try:
        with path.open("r", encoding="utf-8") as f:
            businesses = json.load(f)
    except Exception as exc:
        print(f"[load_businesses] failed to read JSON: {exc}")
        return [], stats

    if not isinstance(businesses, list):
        print(f"[load_businesses] expected list, got {type(businesses).__name__}")
        return [], stats

    seen_ids = set(existing_ids or set())
    out: list[dict[str, Any]] = []
    stats["total_read"] = len(businesses)

    for idx, item in enumerate(businesses):
        if not isinstance(item, dict):
            print(f"[load_businesses] warning: item[{idx}] is not an object; skipped")
            stats["skipped_count"] += 1
            stats["missing_required_skipped"] += 1
            continue

        rid = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        category = str(item.get("category") or "").strip().lower()
        status = str(item.get("status") or "").strip().lower()

        if not rid or not title or not category or not status:
            print(f"[load_businesses] warning: item[{idx}] missing required fields; skipped")
            stats["skipped_count"] += 1
            stats["missing_required_skipped"] += 1
            continue

        if rid in seen_ids:
            stats["skipped_count"] += 1
            stats["duplicates_skipped"] += 1
            continue
        seen_ids.add(rid)

        event_time_raw = item.get("event_time")
        event_time = str(event_time_raw).strip() if event_time_raw is not None else ""
        event_time = event_time or None

        row: dict[str, Any] = {
            "id": rid,
            "event_ref": rid,
            "title": title,
            "description": str(item.get("description") or "").strip(),
            "category": category,
            "status": status,
            "tags": _normalize_tags(item.get("tags")),
            "intent_tags": _normalize_tags(item.get("intent_tags")),
            "location": str(item.get("location") or "").strip() or "Lake Havasu",
            "location_label": str(item.get("location") or "").strip() or "Lake Havasu",
            "source": "real",
            "source_url": str(item.get("source_url") or f"/business/{rid}").strip(),
            "type": "event",
            "event_time": event_time,
            "start_date": event_time or "",
            "end_date": event_time or "",
            "view_count": 0,
            "click_count": 0,
        }
        out.append(row)
        stats["inserted_count"] += 1

    print(
        "[load_businesses] "
        f"total_loaded={stats['inserted_count']} "
        f"duplicates_skipped={stats['duplicates_skipped']} "
        f"skipped_count={stats['skipped_count']}"
    )
    return out, stats


def main() -> None:
    rows, stats = load_businesses()
    print(f"[load_businesses] total_final_dataset_size={len(rows)}")
    print("[load_businesses] sample_items:")
    for row in rows[:3]:
        print(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "category": row.get("category"),
                "status": row.get("status"),
            }
        )
    # Keep output deterministic for script usage.
    if not rows:
        print("[load_businesses] no rows loaded")
    _ = stats


if __name__ == "__main__":
    main()
