from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limit_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full suite exceeds default in-memory limit when sharing one TestClient IP."""
    monkeypatch.setenv("HAVASU_RATE_LIMIT_DISABLED", "1")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-admin-token"}


@pytest.fixture
def fresh_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolated SQLite file + init schema/migrations."""
    import db.database as dbm

    p = tmp_path / "test.db"
    monkeypatch.setattr(dbm, "DB_PATH", p)
    dbm.init_db()
    return p
