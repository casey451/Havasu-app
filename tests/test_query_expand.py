"""Query expansion: static map; optional OpenAI when USE_AI_EXPANSION=1."""
from __future__ import annotations

import sys
import types

import pytest

from core.query_expand import (
    _expand_query_static,
    expand_query,
    match_rows_for_queries,
    raw_payload_dedupe_key,
    should_expand,
)


def test_date_night_expands() -> None:
    expanded = expand_query("date night")
    assert "dinner" in expanded
    assert "nightlife" in expanded
    assert "date night" in expanded


def test_should_expand_low_confidence() -> None:
    assert should_expand({"confidence": 0.1}, "anything goes here many words") is True


def test_should_expand_short_query() -> None:
    assert should_expand({"confidence": 0.9}, "ab") is True


def test_should_expand_skips_only_strong_non_discovery_long_query() -> None:
    assert should_expand({"confidence": 0.9}, "this is a very long phrase now") is False


def test_dedupe_key_stable() -> None:
    a = {"user_event_id": 5, "title": "X"}
    b = {"user_event_id": 5, "title": "Y"}
    assert raw_payload_dedupe_key(a) == raw_payload_dedupe_key(b)


def test_expand_static_matches_expand_query_when_ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USE_AI_EXPANSION", raising=False)
    assert expand_query("date night") == _expand_query_static("date night")


def test_ai_expand_falls_back_when_openai_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """If OpenAI client fails, expand_query matches static map (no dependency on real SDK)."""
    fake = types.ModuleType("openai")

    def boom_openai(*_a: object, **_k: object) -> None:
        raise RuntimeError("no API")

    fake.OpenAI = boom_openai
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("USE_AI_EXPANSION", "1")
    assert expand_query("date night") == _expand_query_static("date night")


def test_match_rows_dedupes() -> None:
    rows = [
        {"title": "Dinner at Pier", "item_db_id": 1, "source_url": "http://a"},
        {"title": "Dinner at Pier", "item_db_id": 1, "source_url": "http://a"},
    ]
    out = match_rows_for_queries(rows, ["dinner", "pier"])
    assert len(out) == 1


def test_match_rows_uses_description_and_tags_blob() -> None:
    rows = [
        {
            "title": "Lake Havasu Home Services",
            "description": "Emergency repair and maintenance tonight",
            "tags": ["plumbing", "hvac"],
            "item_db_id": 7,
            "source_url": "http://example.com/p",
        }
    ]
    out = match_rows_for_queries(rows, ["plumber", "tonight"])
    assert len(out) == 1
