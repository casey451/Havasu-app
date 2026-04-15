"""Business profile entities: validation, tagging, event linkage."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from core.passwords import hash_password


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
    monkeypatch.setenv("HAVASU_JWT_SECRET", "test-jwt-secret-bprof")
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


def test_create_business_requires_fields(client: TestClient) -> None:
    tok = _approve_biz(client, f"req_{uuid.uuid4().hex[:10]}@test.com")
    r = client.post(
        "/business/create",
        headers={"Authorization": f"Bearer {tok}"},
        json={"name": "Only Name", "description": "x" * 20, "category": ""},
    )
    assert r.status_code == 422
    r2 = client.post(
        "/business/create",
        headers={"Authorization": f"Bearer {tok}"},
        json={"description": "Some text here for the business.", "category": "HVAC"},
    )
    assert r2.status_code == 422


def test_business_tags_inferred(client: TestClient) -> None:
    tok = _approve_biz(client, f"tags_{uuid.uuid4().hex[:10]}@test.com")
    r = client.post(
        "/business/create",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "Cool Zone HVAC",
            "description": "Family-friendly service for home heating and cooling.",
            "category": "HVAC repair",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    tags = data.get("tags") or []
    assert "kids" in tags
    assert data.get("category_group") == "Home Services"


def test_event_links_to_business(client: TestClient) -> None:
    tok = _approve_biz(client, f"link_{uuid.uuid4().hex[:10]}@test.com")
    cr = client.post(
        "/business/create",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "Lake Bites Cafe",
            "description": "Breakfast and lunch by the water.",
            "category": "Breakfast",
        },
    )
    assert cr.status_code == 201, cr.text
    pid = cr.json()["id"]

    ev = client.post(
        "/business/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "title": "Sunday brunch special",
            "description": "Join us for pancakes and live acoustic music.",
            "start_date": "2026-12-01",
            "start_time": "09:00",
            "location_label": "Waterfront",
        },
    )
    assert ev.status_code == 201, ev.text
    assert ev.json().get("business_profile_id") == pid

    items = client.get("/items", params={"type": "event"}).json()
    user_rows = [x for x in items if x.get("source") == "user"]
    assert user_rows
    hit = next((x for x in user_rows if x.get("title") == "Sunday brunch special"), None)
    assert hit is not None
    assert hit.get("business_name") == "Lake Bites Cafe"
    assert hit.get("business_category") == "Food & Drink"
