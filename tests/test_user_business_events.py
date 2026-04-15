"""Business-created events: trust, validation, tags."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from core.passwords import hash_password
from core.serialize import normalize_item
from core.tags import infer_tags


def _seed_admin(db_path: str) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO businesses (email, password_hash, name, role, status, created_at, updated_at)
        VALUES (?, ?, 'Admin', 'admin', 'approved', ?, ?)
        """,
        ("admin@test.com", hash_password("adminpass12"), now, now),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def client(fresh_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("HAVASU_JWT_SECRET", "test-jwt-secret-ubiz")
    _seed_admin(str(fresh_db))
    from api.main import app

    return TestClient(app)


def _approve_biz(client: TestClient, email: str) -> str:
    r_reg = client.post(
        "/auth/register",
        json={"email": email, "password": "password12", "name": "Biz"},
    )
    assert r_reg.status_code == 201, r_reg.text
    from db.database import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT id FROM businesses WHERE email = ?", (email,)).fetchone()
    assert row is not None
    client.post(
        f"/admin/approve-business/{int(row['id'])}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    return client.post(
        "/auth/login", json={"email": email, "password": "password12"}
    ).json()["access_token"]


def test_user_event_has_trust_1() -> None:
    n = normalize_item(
        {
            "type": "event",
            "title": "Biz Event",
            "start_date": "2026-08-01",
            "source": "user",
            "user_event_id": 1,
            "description": "Live music night",
        }
    )
    assert n["trust_score"] == 1.0
    assert n["source"] == "user"


def test_user_event_requires_date(client: TestClient) -> None:
    tok = _approve_biz(client, f"nodate_{uuid.uuid4().hex[:10]}@test.com")
    r = client.post(
        "/business/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "title": "X",
            "description": "Has description and location.",
            "location_label": "Here",
        },
    )
    assert r.status_code == 422


def test_user_event_tags_applied(client: TestClient) -> None:
    tok = _approve_biz(client, f"tags_{uuid.uuid4().hex[:10]}@test.com")
    r = client.post(
        "/business/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "title": "Family concert night",
            "description": "Outdoor show for everyone.",
            "start_date": "2026-07-04",
            "start_time": "19:00",
            "location_label": "Park",
            "tags": ["custom"],
        },
    )
    assert r.status_code == 201
    tags = r.json().get("tags") or []
    assert "custom" in tags
    assert "kids" in tags or "music" in tags
    assert "music" in infer_tags("Family concert night", "Outdoor show for everyone.")
