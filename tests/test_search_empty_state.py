"""Search UX safety for sparse databases: fallback rows + stable response shape."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import SearchResponse, app
from core.ai_helper import generate_suggestions
from core.query_expand import should_expand


def test_generate_plumbing_empty_uses_category_copy() -> None:
    out = generate_suggestions("plumber", {"category": "plumbing", "confidence": 0.5}, [])
    assert out["suggestions"][0] == "No plumbers found yet"
    assert len(out["suggestions"]) == 3


def test_search_plumber_no_db_rows_returns_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.main._combined_read_rows", lambda *a, **k: [])
    c = TestClient(app)
    r = c.get("/search", params={"q": "plumber"})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert "ai" in body
    assert isinstance(body["results"], list)
    assert len(body["results"]) >= 1
    assert body["results"][0]["source"] == "fallback"


def test_search_food_tonight_expands_and_matches_description_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_rows = [
        {
            "title": "Local Services Hub",
            "description": "Great places to eat tonight around town",
            "tags": ["dining", "food"],
            "type": "event",
            "start_date": "",
            "end_date": "",
            "weekday": "",
            "start_time": "",
            "end_time": "",
            "source": "user",
            "source_url": "https://example.com/f1",
            "location_label": "",
            "category": "food",
        }
    ]
    monkeypatch.setattr("api.main._combined_read_rows", lambda *a, **k: fake_rows)
    c = TestClient(app)
    r = c.get("/search", params={"q": "food tonight"})
    assert r.status_code == 200
    body = r.json()
    assert should_expand({"confidence": 0.42, "category": "food"}, "food tonight")
    assert len(body["results"]) == 1
    assert body["results"][0]["source"] != "fallback"


def test_search_discovery_uses_fallback_when_db_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.main._combined_read_rows", lambda *a, **k: [])
    c = TestClient(app)
    r = c.get("/search", params={"q": "things to do this weekend"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]
    assert body["results"][0]["source"] == "fallback"


def test_search_shape_stable_with_ai_null(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.main.should_use_ai", lambda _r, _i: False)
    monkeypatch.setattr("api.main._combined_read_rows", lambda *a, **k: [])
    c = TestClient(app)
    r = c.get("/search", params={"q": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert "ai" in body
    assert isinstance(body["results"], list)
    assert body["ai"] is None


def test_search_exception_returns_safe_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.main._combined_read_rows", MagicMock(side_effect=RuntimeError("db")))
    c = TestClient(app)
    r = c.get("/search", params={"q": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"] == []
    assert body["ai"] is not None
    assert len(body["ai"]["suggestions"]) == 3


def test_search_response_model_has_defaults() -> None:
    m = SearchResponse()
    assert m.results == []
    assert m.ai is None
