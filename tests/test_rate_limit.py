from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def _submit_payload(i: int) -> dict:
    return {
        "title": f"Rate Limit Submission {i}",
        "description": "rl test",
        "tags": ["rl"],
        "category": "service",
        "start_date": "2026-06-15",
        "location": "Lake Havasu",
    }


def test_submit_under_limit_succeeds(fresh_db, monkeypatch) -> None:
    _ = fresh_db
    monkeypatch.setenv("HAVASU_RATE_LIMIT_DISABLED", "0")
    c = TestClient(app)
    headers = {"x-forwarded-for": "10.0.0.11"}
    for i in range(10):
        r = c.post("/submit", json=_submit_payload(i), headers=headers)
        assert r.status_code == 200


def test_submit_over_limit_returns_429(fresh_db, monkeypatch) -> None:
    _ = fresh_db
    monkeypatch.setenv("HAVASU_RATE_LIMIT_DISABLED", "0")
    c = TestClient(app)
    headers = {"x-forwarded-for": "10.0.0.12"}
    for i in range(10):
        r = c.post("/submit", json=_submit_payload(100 + i), headers=headers)
        assert r.status_code == 200
    r_over = c.post("/submit", json=_submit_payload(999), headers=headers)
    assert r_over.status_code == 429
    assert r_over.json() == {"error": "rate_limited"}


def test_rate_limit_is_per_ip(fresh_db, monkeypatch) -> None:
    _ = fresh_db
    monkeypatch.setenv("HAVASU_RATE_LIMIT_DISABLED", "0")
    c = TestClient(app)
    ip_a = {"x-forwarded-for": "10.0.0.21"}
    ip_b = {"x-forwarded-for": "10.0.0.22"}
    for i in range(10):
        assert c.post("/submit", json=_submit_payload(200 + i), headers=ip_a).status_code == 200
    assert c.post("/submit", json=_submit_payload(299), headers=ip_a).status_code == 429
    assert c.post("/submit", json=_submit_payload(300), headers=ip_b).status_code == 200


def test_track_view_over_limit_returns_429(fresh_db, monkeypatch) -> None:
    _ = fresh_db
    monkeypatch.setenv("HAVASU_RATE_LIMIT_DISABLED", "0")
    c = TestClient(app)
    headers = {"x-forwarded-for": "10.0.0.31"}
    for _ in range(60):
        r = c.post("/track/view", json={"id": "missing-id"}, headers=headers)
        assert r.status_code == 200
    r_over = c.post("/track/view", json={"id": "missing-id"}, headers=headers)
    assert r_over.status_code == 429
    assert r_over.json() == {"error": "rate_limited"}
