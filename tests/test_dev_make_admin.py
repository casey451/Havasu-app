from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from core.passwords import hash_password
from db.accounts import create_business


def test_dev_make_admin_promotes_user_without_auth(fresh_db) -> None:
    _ = fresh_db
    create_business(
        email="caseysolomon@gmail.com",
        password_hash=hash_password("Password123!"),
        name="Casey",
        role="business",
        status="approved",
    )
    c = TestClient(app)
    r = c.post("/dev/make-admin", json={"email": "caseysolomon@gmail.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "caseysolomon@gmail.com"
    assert body["role"] == "admin"


def test_dev_make_admin_missing_user(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    r = c.post("/dev/make-admin", json={"email": "missing@example.com"})
    assert r.status_code == 404
