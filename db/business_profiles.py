from __future__ import annotations

import json
import uuid
from typing import Any

from db.database import get_connection, utc_now_iso


def _parse_tags(raw: Any) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    try:
        p = json.loads(raw)
        if not isinstance(p, list):
            return []
        return [str(x).strip() for x in p if str(x).strip()]
    except (json.JSONDecodeError, TypeError):
        return []


def get_profile_id_for_owner(owner_business_id: int) -> str | None:
    """Profile id for linking new events — only when listing is active."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM business_profiles
            WHERE owner_business_id = ? AND is_active = 1
            """,
            (owner_business_id,),
        ).fetchone()
        return str(row["id"]) if row else None


def get_profile_row_for_owner(owner_business_id: int) -> dict[str, Any] | None:
    """Owner's profile row if any (including inactive)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM business_profiles WHERE owner_business_id = ?",
            (owner_business_id,),
        ).fetchone()
        return dict(row) if row else None


def get_profile_by_id(profile_id: str) -> dict[str, Any] | None:
    pid = (profile_id or "").strip()
    if not pid:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM business_profiles WHERE id = ?",
            (pid,),
        ).fetchone()
        return dict(row) if row else None


def list_active_profiles(*, limit: int = 200) -> list[dict[str, Any]]:
    lim = max(1, min(limit, 500))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM business_profiles
            WHERE is_active = 1
            ORDER BY name COLLATE NOCASE, id
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_profile(
    *,
    owner_business_id: int,
    name: str,
    description: str,
    category: str,
    category_group: str,
    tags_json: str,
    phone: str | None,
    website: str | None,
    address: str | None,
    city: str,
    is_active: bool = True,
) -> str:
    pid = str(uuid.uuid4())
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO business_profiles (
              id, owner_business_id, name, description, category, category_group,
              tags, phone, website, address, city, is_active, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                owner_business_id,
                name.strip(),
                description.strip(),
                category.strip(),
                category_group.strip(),
                tags_json,
                phone.strip() if phone else None,
                website.strip() if website else None,
                address.strip() if address else None,
                city.strip() or "Lake Havasu",
                1 if is_active else 0,
                now,
            ),
        )
        conn.commit()
    return pid


def update_profile_for_owner(
    owner_business_id: int,
    *,
    name: str,
    description: str,
    category: str,
    category_group: str,
    tags_json: str,
    phone: str | None,
    website: str | None,
    address: str | None,
    city: str,
    is_active: bool,
) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE business_profiles SET
              name = ?, description = ?, category = ?, category_group = ?,
              tags = ?, phone = ?, website = ?, address = ?, city = ?, is_active = ?
            WHERE owner_business_id = ?
            """,
            (
                name.strip(),
                description.strip(),
                category.strip(),
                category_group.strip(),
                tags_json,
                phone.strip() if phone else None,
                website.strip() if website else None,
                address.strip() if address else None,
                city.strip() or "Lake Havasu",
                1 if is_active else 0,
                owner_business_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def profile_to_public_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "description": str(row["description"]),
        "category": str(row["category"]),
        "category_group": str(row["category_group"]),
        "tags": _parse_tags(row.get("tags")),
        "phone": row.get("phone"),
        "website": row.get("website"),
        "address": row.get("address"),
        "city": str(row.get("city") or "Lake Havasu"),
        "is_active": bool(int(row.get("is_active") or 0)),
        "created_at": str(row["created_at"]),
    }
