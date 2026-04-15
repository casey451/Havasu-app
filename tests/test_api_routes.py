from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def test_search_requires_q() -> None:
    c = TestClient(app)
    r = c.get("/search")
    assert r.status_code == 422


def test_items_returns_normalized_by_default() -> None:
    c = TestClient(app)
    r = c.get("/items", params={"limit": 3})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if not data:
        return
    row = data[0]
    assert "source_url" in row
    assert "title" in row
    assert "type" in row


def test_today_returns_structure() -> None:
    c = TestClient(app)
    r = c.get("/today")
    assert r.status_code == 200
    body = r.json()
    assert "date" in body and "events" in body and "recurring" in body
