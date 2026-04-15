"""Unit tests for core.intent_map (PHASE 1 intent mapping)."""
from __future__ import annotations

from core.intent_map import INTENT_KEYWORDS, parse_intent


def test_intent_keywords_minimum_categories() -> None:
    keys = set(INTENT_KEYWORDS)
    for k in ("hvac", "plumbing", "electrical", "food", "nightlife", "kids", "sports", "events"):
        assert k in keys


def test_hvac_query() -> None:
    out = parse_intent("Need HVAC repair before summer")
    assert "hvac" in out["tags"]
    assert out["category"] == "hvac"
    assert out["confidence"] > 0.2


def test_food_query() -> None:
    out = parse_intent("Best coffee and breakfast near the lake")
    assert "food" in out["tags"]
    assert out["category"] == "food"
    assert out["confidence"] > 0.3


def test_kids_query() -> None:
    # Avoid "weekend" so `events` does not tie and win lexicographically over `kids`.
    out = parse_intent("Activities for children and toddlers")
    assert "kids" in out["tags"]
    assert out["category"] == "kids"
    assert out["confidence"] > 0.2


def test_no_match_returns_low_confidence() -> None:
    out = parse_intent("asdf qwerty zzzz")
    assert out["tags"] == []
    assert out["category"] is None
    assert out["confidence"] <= 0.1
