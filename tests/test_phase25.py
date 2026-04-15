from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from core.passwords import hash_password


def _seed_admin(db_path: str, email: str, password: str) -> None:
    conn = sqlite3.connect(db_path)
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO businesses (email, password_hash, name, role, status, created_at, updated_at)
        VALUES (?, ?, 'Admin', 'admin', 'approved', ?, ?)
        """,
        (email, hash_password(password), now, now),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def client(fresh_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("HAVASU_JWT_SECRET", "test-jwt-secret-phase25")
    _seed_admin(str(fresh_db), "admin@test.com", "adminpass12")
    from api.main import app

    return TestClient(app)


def test_register_login_me(client: TestClient) -> None:
    r = client.post(
        "/auth/register",
        json={"email": "biz@test.com", "password": "password12", "name": "Cool Biz"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"

    r2 = client.post(
        "/auth/login", json={"email": "admin@test.com", "password": "adminpass12"}
    )
    assert r2.status_code == 200
    tok = r2.json()["access_token"]

    r3 = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r3.status_code == 200
    assert r3.json()["role"] == "admin"


def test_approve_then_create_event(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "owner@test.com", "password": "password12", "name": "Owner"},
    )
    bid = client.post(
        "/auth/login", json={"email": "owner@test.com", "password": "password12"}
    ).json()
    # pending cannot create
    r_block = client.post(
        "/business/events",
        headers={"Authorization": f"Bearer {bid['access_token']}"},
        json={
            "title": "Blocked",
            "start_date": "2026-06-01",
        },
    )
    assert r_block.status_code == 403

    # find business id
    from db.database import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM businesses WHERE email = ?", ("owner@test.com",)
        ).fetchone()
    assert row is not None
    business_id = int(row["id"])

    client.post(
        f"/admin/approve-business/{business_id}",
        headers={"Authorization": "Bearer test-admin-token"},
    )

    tok = client.post(
        "/auth/login", json={"email": "owner@test.com", "password": "password12"}
    ).json()["access_token"]

    r_ok = client.post(
        "/business/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "title": "Summer Bash",
            "description": "Fun <b>times</b>",
            "start_date": "2026-06-15",
            "start_time": "18:00",
            "location_label": "Downtown",
        },
    )
    assert r_ok.status_code == 201
    ev = r_ok.json()
    assert "times" in ev["description"] and "<b>" not in (ev["description"] or "")

    eid = ev["id"]
    r_put = client.put(
        f"/business/events/{eid}",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "title": "Summer Bash 2",
            "description": "Updated description for the bash.",
            "start_date": "2026-06-15",
            "start_time": "18:00",
            "location_label": "Downtown",
        },
    )
    assert r_put.status_code == 200
    assert r_put.json()["title"] == "Summer Bash 2"


def test_strip_html_validation() -> None:
    from api.validation import clamp_description, clamp_title

    assert clamp_title("<h1>Hi</h1>", 120) == "Hi"
    assert clamp_description("<p>x</p>y", 2000) == "xy"


def test_jwt_production_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAVASU_ENV", "production")
    monkeypatch.delenv("HAVASU_JWT_SECRET", raising=False)
    from api.security import create_access_token

    with pytest.raises(RuntimeError, match="HAVASU_JWT_SECRET"):
        create_access_token(user_id=1, role="business", email="x@y.com")


def test_user_event_on_today_after_approve(client: TestClient) -> None:
    """Business-created events appear on GET /today alongside crawler data."""
    client.post(
        "/auth/register",
        json={"email": "pub@test.com", "password": "password12", "name": "Pub Biz"},
    )
    from db.database import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM businesses WHERE email = ?", ("pub@test.com",)
        ).fetchone()
    assert row is not None
    bid = int(row["id"])
    client.post(
        f"/admin/approve-business/{bid}",
        headers={"Authorization": "Bearer test-admin-token"},
    )
    tok = client.post(
        "/auth/login", json={"email": "pub@test.com", "password": "password12"}
    ).json()["access_token"]
    day = date.today().isoformat()
    client.post(
        "/business/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "title": "User Posted Today",
            "description": "hello",
            "start_date": day,
            "start_time": "12:00",
            "location_label": "Main St",
        },
    )
    r = client.get("/today")
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()["events"]]
    assert "User Posted Today" in titles
    srcs = [e.get("source") for e in r.json()["events"] if e["title"] == "User Posted Today"]
    assert srcs == ["user"]
