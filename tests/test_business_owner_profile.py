"""Owner GET/PUT /business/me and public list behavior."""
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
    monkeypatch.setenv("HAVASU_JWT_SECRET", "test-jwt-secret-owner-prof")
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


def test_owner_get_me_404_without_profile(client: TestClient) -> None:
    tok = _approve_biz(client, f"nome_{uuid.uuid4().hex[:10]}@test.com")
    r = client.get("/business/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404


def test_owner_can_create_profile_via_put_me(client: TestClient) -> None:
    tok = _approve_biz(client, f"create_{uuid.uuid4().hex[:10]}@test.com")
    r = client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "Desert HVAC",
            "description": "We fix air conditioning for local families.",
            "category": "HVAC",
            "is_active": True,
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Desert HVAC"
    assert data["category_group"] == "Home Services"
    g = client.get("/business/me", headers={"Authorization": f"Bearer {tok}"})
    assert g.status_code == 200
    assert g.json()["id"] == data["id"]


def test_owner_can_update_own_profile(client: TestClient) -> None:
    tok = _approve_biz(client, f"upd_{uuid.uuid4().hex[:10]}@test.com")
    client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "First Name",
            "description": "Original description for the business here.",
            "category": "Plumbing",
            "city": "Lake Havasu",
            "is_active": True,
        },
    )
    r2 = client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "Renamed Co",
            "description": "Updated description with music and concert nights.",
            "category": "Plumbing",
            "is_active": True,
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["name"] == "Renamed Co"
    pid = r2.json()["id"]
    r3 = client.get(f"/business/{pid}")
    assert r3.status_code == 200
    assert r3.json()["name"] == "Renamed Co"


def test_profile_tags_inferred_on_put_me_update(client: TestClient) -> None:
    tok = _approve_biz(client, f"tags_{uuid.uuid4().hex[:10]}@test.com")
    client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "X",
            "description": "Basic plumbing.",
            "category": "Plumber",
            "is_active": True,
        },
    )
    r = client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "name": "X",
            "description": "We host live music and concerts for families with kids.",
            "category": "Plumber",
            "is_active": True,
        },
    )
    assert r.status_code == 200
    tags = r.json().get("tags") or []
    assert "kids" in tags
    assert "music" in tags


def test_public_list_returns_active_profiles_only(client: TestClient) -> None:
    tok_a = _approve_biz(client, f"act_{uuid.uuid4().hex[:8]}@test.com")
    tok_b = _approve_biz(client, f"hid_{uuid.uuid4().hex[:8]}@test.com")
    client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={
            "name": "Visible Shop",
            "description": "Open for business.",
            "category": "Restaurant",
            "is_active": True,
        },
    )
    client.put(
        "/business/me",
        headers={"Authorization": f"Bearer {tok_b}"},
        json={
            "name": "Hidden Shop",
            "description": "Temporarily hidden.",
            "category": "Restaurant",
            "is_active": False,
        },
    )
    lst = client.get("/business/list").json()
    names = {x["name"] for x in lst}
    assert "Visible Shop" in names
    assert "Hidden Shop" not in names
