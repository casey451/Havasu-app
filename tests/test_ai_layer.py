"""AI fallback gating and stub suggestions (no external API)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from core.ai_helper import generate_suggestions, should_use_ai


def test_ai_triggers_on_empty() -> None:
    intent = {"confidence": 0.1}
    results: list = []
    assert should_use_ai(results, intent) is True


def test_ai_skips_when_strong_results() -> None:
    intent = {"confidence": 0.8}
    results = [{"title": "Something"}]
    assert should_use_ai(results, intent) is False


def test_ai_triggers_on_low_confidence_even_with_results() -> None:
    intent = {"confidence": 0.1}
    results = [{"title": "X"}]
    assert should_use_ai(results, intent) is True


def test_generate_suggestions_stub_returns_list() -> None:
    out = generate_suggestions("q", {"category": "food"}, [])
    assert "suggestions" in out
    assert isinstance(out["suggestions"], list)
    assert len(out["suggestions"]) <= 3
    assert "food" in out["suggestions"][0].lower() or "dining" in out["suggestions"][0].lower()


def test_search_response_shape() -> None:
    from api.main import app

    c = TestClient(app)
    r = c.get("/search", params={"q": "music"})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert isinstance(body["results"], list)
    assert "ai" in body
