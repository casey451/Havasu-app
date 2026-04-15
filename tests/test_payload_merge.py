from __future__ import annotations

from core.payload_merge import merge_event_payloads, title_similarity_ratio
from core.serialize import normalize_item


def test_merge_combines_description_and_urls() -> None:
    golake = {
        "source": "golakehavasu",
        "type": "event",
        "title": "Havasu Stingrays Swim Team Tryout",
        "start_date": "2026-04-18",
        "end_date": "2026-04-18",
        "start_time": "10:30",
        "end_time": "11:30",
        "venue_name": "Aquatic Center",
        "address": "100 Park Ave",
        "description": None,
        "source_url": "https://golake.example/e",
    }
    river = {
        "source": "riverscene",
        "type": "event",
        "title": "Havasu Stingrays Swim Team Try Outs",
        "start_date": "2026-04-15",
        "end_date": "2026-04-15",
        "start_time": "10:30",
        "end_time": "11:30",
        "description": "Free practice week April 20–24. Ages 6–18.",
        "source_url": "https://river.example/e",
    }
    m = merge_event_payloads(golake, river)
    assert "Free practice week" in (m.get("description") or "")
    assert "https://golake.example/e" in m["source_urls"]
    assert "https://river.example/e" in m["source_urls"]
    assert m["start_date"] == "2026-04-18"


def test_title_similarity_stingrays() -> None:
    a = "Havasu Stingrays Swim Team Tryout"
    b = "Havasu Stingrays Swim Team Try Outs"
    assert title_similarity_ratio(a, b) >= 0.86


def test_normalize_uses_venue_when_location_label_empty() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "X",
            "start_date": "2026-01-01",
            "source": "golakehavasu",
            "source_url": "https://x",
            "venue_name": "Aquatic Center",
            "address": "100 Park Ave",
            "location_label": None,
        }
    )
    assert "Aquatic" in n["location_label"]
    assert n["has_location"] is True
    assert "description" in n
