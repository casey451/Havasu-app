from __future__ import annotations

import pytest

from core.serialize import normalize_item


def test_normalize_item_shape() -> None:
    n = normalize_item(
        {
            "source": "havasu_parks",
            "type": "recurring",
            "title": "Lap Swim",
            "weekday": "Monday",
            "start_time": "06:00",
            "end_time": "08:00",
            "start_date": None,
            "source_url": "https://example.com",
            "location_label": "Pool",
        }
    )
    assert set(n.keys()) >= {
        "title",
        "type",
        "start_date",
        "end_date",
        "weekday",
        "start_time",
        "end_time",
        "location_label",
        "source",
        "source_url",
        "date",
        "has_start_time",
        "has_end_time",
        "has_location",
    }
    assert n["type"] == "recurring"
    assert n["date"] == ""
    assert n["title"] == "Lap Swim"
    assert n["has_start_time"] is True
    assert n["has_end_time"] is True
    assert n["has_location"] is True


def test_normalize_event_has_date_alias() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "X",
            "start_date": "2026-06-01",
            "source": "riverscene",
            "source_url": "https://x.com/e",
        }
    )
    assert n["date"] == "2026-06-01"
    assert n["start_date"] == "2026-06-01"
    assert n["has_start_time"] is False
    assert n["has_end_time"] is False
    assert n["has_location"] is False


def test_has_location_true_when_venue_only_no_label() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "Gym Night",
            "start_date": "2026-08-01",
            "source": "golakehavasu",
            "location_label": "",
            "venue_name": "Main Gym",
            "address": "",
        }
    )
    assert n["has_location"] is True
    assert "Main Gym" in n["location_label"]


def test_user_event_includes_business_id_and_location_from_venue() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "Class",
            "start_date": "2026-09-01",
            "source": "user",
            "business_id": 42,
            "location_label": "",
            "venue_name": "Aquatic Center",
            "address": "",
            "source_url": "",
        }
    )
    assert n["business_id"] == 42
    assert n["has_location"] is True
    assert n["location_label"] == "Aquatic Center"


def test_event_ref_from_ids() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "X",
            "start_date": "2026-01-01",
            "source": "riverscene",
            "item_db_id": 99,
        }
    )
    assert n.get("event_ref") == "c-99"
    u = normalize_item(
        {
            "type": "event",
            "title": "Y",
            "start_date": "2026-01-02",
            "source": "user",
            "business_id": 1,
            "user_event_id": 7,
        }
    )
    assert u.get("event_ref") == "u-7"


def test_debug_source_type_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAVASU_API_DEBUG_SOURCE", "1")
    a = normalize_item({"type": "event", "title": "A", "start_date": "2026-01-01", "source": "riverscene"})
    b = normalize_item(
        {"type": "event", "title": "B", "start_date": "2026-01-01", "source": "user", "business_id": 1}
    )
    assert a.get("debug_source_type") == "crawler"
    assert b.get("debug_source_type") == "user"
