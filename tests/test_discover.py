from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.discover import get_fallback_rows, get_popular, get_today, get_weekend


def _row(title: str, start_date: str, trust_score: float = 0.0) -> dict:
    return {
        "activity_id": f"a-{title.replace(' ', '-').lower()}",
        "title": title,
        "type": "event",
        "start_date": start_date,
        "end_date": start_date,
        "weekday": "",
        "start_time": "",
        "end_time": "",
        "location_label": "",
        "source": "golakehavasu",
        "source_url": f"https://example.com/{title}",
        "description": title,
        "tags": [],
        "category": "events",
        "has_start_time": False,
        "has_end_time": False,
        "has_location": False,
        "trust_score": trust_score,
    }


def test_get_today_filters_to_today() -> None:
    today = datetime.now(UTC).date().isoformat()
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    rows = [_row("today item", today), _row("tomorrow item", tomorrow)]
    out = get_today(rows)
    assert len(out) == 1
    assert out[0]["title"] == "today item"


def test_get_weekend_filters_to_this_week() -> None:
    today = datetime.now(UTC).date()
    in_window = (today + timedelta(days=1)).isoformat()
    out_window = (today + timedelta(days=10)).isoformat()
    rows = [_row("soon", in_window), _row("later", out_window)]
    out = get_weekend(rows)
    titles = [x["title"] for x in out]
    assert "soon" in titles
    assert "later" not in titles


def test_get_popular_fallback_when_empty() -> None:
    out = get_popular([])
    assert out == get_fallback_rows()
    assert out[0]["source"] == "fallback"


def test_discover_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.main._combined_read_rows", lambda *a, **k: [])
    c = TestClient(app)
    r = c.get("/discover")
    assert r.status_code == 200
    body = r.json()
    assert "today" in body and isinstance(body["today"], list)
    assert "weekend" in body and isinstance(body["weekend"], list)
    assert "popular" in body and isinstance(body["popular"], list)
    assert body["popular"]
    row = body["popular"][0]
    for key in ("title", "description", "tags", "start_date", "source", "type"):
        assert key in row


def test_get_popular_caps_featured_count() -> None:
    today = datetime.now(UTC).date().isoformat()
    rows = []
    for i in range(5):
        rows.append(
            {
                **_row(f"featured-{i}", today, trust_score=10 - i),
                "is_featured": True,
                "featured_until": "2099-01-01T00:00:00+00:00",
                "id": f"f-{i}",
            }
        )
    rows.append({**_row("normal-a", today, trust_score=9), "id": "n-a"})
    out = get_popular(rows, limit=10)
    featured = [r for r in out[:5] if r.get("is_featured")]
    assert len(featured) <= 3


def test_get_popular_prefers_new_relevant_over_stale_historical() -> None:
    today = datetime.now(UTC).date()
    rows = [
        {
            **_row("new event", (today + timedelta(days=1)).isoformat(), trust_score=0.9),
            "view_count": 5,
            "click_count": 2,
            "id": "new",
        },
        {
            **_row("stale old event", (today - timedelta(days=40)).isoformat(), trust_score=0.9),
            "view_count": 50000,
            "click_count": 5000,
            "id": "old",
        },
    ]
    out = get_popular(rows, limit=10)
    assert out[0]["id"] == "new"
