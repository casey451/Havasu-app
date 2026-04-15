"""Tags, trust_score, normalized API shape, homepage sort (foundation pass)."""
from __future__ import annotations

from core.serialize import homepage_calendar_sort_key, normalize_item
from core.tags import infer_tags
from core.trust_score import compute_trust_score


def test_tags_added_from_crawler() -> None:
    assert "kids" in infer_tags("Family Fun Day", "Bring the kids for games")
    assert "music" in infer_tags("Live DJ Night", "concert at the park")
    assert "social" in infer_tags("Trivia night", "game night with prizes")
    assert "sports" in infer_tags("5k race", "fun run for charity")


def test_trust_score_assignment() -> None:
    assert compute_trust_score({"source": "user"}) == 1.0
    assert (
        compute_trust_score({"source": "riverscene", "riverscene_date_confidence": "high"})
        == 0.7
    )
    assert (
        compute_trust_score({"source": "riverscene", "riverscene_date_confidence": "medium"})
        == 0.5
    )
    assert (
        compute_trust_score({"source": "riverscene", "riverscene_date_confidence": "low"})
        == 0.2
    )
    assert compute_trust_score({"source": "golakehavasu", "high_confidence": True}) == 0.7
    assert compute_trust_score({"source": "golakehavasu"}) == 0.5


def test_event_shape_consistency() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "Test",
            "start_date": "2026-06-01",
            "source": "riverscene",
            "riverscene_date_confidence": "high",
            "item_db_id": 42,
            "description": "A concert for families",
        }
    )
    for key in (
        "id",
        "title",
        "description",
        "location",
        "start_date",
        "end_date",
        "start_time",
        "tags",
        "category",
        "source",
        "trust_score",
    ):
        assert key in n
    assert n["id"] == "c-42"
    assert isinstance(n["tags"], list)
    assert n["trust_score"] == 0.7


def test_sorting_prefers_high_trust() -> None:
    a = {"start_time": "10:00", "source": "golakehavasu", "trust_score": 0.7, "title": "B"}
    b = {"start_time": "10:00", "source": "user", "trust_score": 1.0, "title": "A"}
    rows = sorted([a, b], key=homepage_calendar_sort_key)
    assert rows[0]["source"] == "user"
