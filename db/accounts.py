from __future__ import annotations

import sqlite3
from typing import Any, Literal

from core.user_event_map import map_user_event_row_to_item_payload
from db.database import get_connection, utc_now_iso

Role = Literal["admin", "business"]
Status = Literal["pending", "approved", "rejected"]


def get_business_by_id(bid: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM businesses WHERE id = ?", (bid,)).fetchone()
        return dict(row) if row else None


def get_business_by_email(email: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM businesses WHERE lower(trim(email)) = lower(trim(?))",
            (email,),
        ).fetchone()
        return dict(row) if row else None


def create_business(
    *,
    email: str,
    password_hash: str,
    name: str,
    role: Role = "business",
    status: Status = "pending",
) -> int:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO businesses (email, password_hash, name, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email.strip().lower(), password_hash, name.strip(), role, status, now, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_business_status(bid: int, status: Status) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE businesses SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, bid),
        )
        conn.commit()
        return cur.rowcount > 0


def update_business_role_by_email(email: str, role: Role) -> dict[str, Any] | None:
    now = utc_now_iso()
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM businesses WHERE lower(trim(email)) = lower(trim(?))",
            (normalized,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE businesses SET role = ?, updated_at = ? WHERE id = ?",
            (role, now, int(row["id"])),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT id, email, name, role, status FROM businesses WHERE id = ?",
            (int(row["id"]),),
        ).fetchone()
        return dict(updated) if updated else None


def list_pending_business_ids() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM businesses WHERE role = 'business' AND status = 'pending' ORDER BY id"
        ).fetchall()
        return [int(r["id"]) for r in rows]


def list_pending_business_accounts() -> list[dict[str, Any]]:
    """Pending business signups (for admin UI)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, email, name, status
            FROM businesses
            WHERE role = 'business' AND status = 'pending'
            ORDER BY id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def count_admins() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM businesses WHERE role = 'admin'"
        ).fetchone()
        return int(row["n"]) if row else 0


# --- user_events ---


def create_user_event(
    *,
    business_id: int,
    title: str,
    description: str | None,
    start_date: str,
    start_time: str | None,
    end_time: str | None,
    location_label: str | None,
    venue_name: str | None = None,
    address: str | None = None,
    tags_json: str | None = None,
    category: str | None = None,
    business_profile_id: str | None = None,
) -> int:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO user_events (
              business_id, business_profile_id, title, description, start_date, start_time, end_time,
              location_label, venue_name, address, tags, category, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                business_id,
                business_profile_id,
                title,
                description,
                start_date,
                start_time,
                end_time,
                location_label,
                venue_name,
                address,
                tags_json,
                category,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_user_event(event_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM user_events WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None


def get_user_event_with_profile_fields(event_id: int) -> dict[str, Any] | None:
    """Single user_event row plus optional `bp_name` / `bp_category_group` for public payloads."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT ue.*, bp.name AS bp_name, bp.category_group AS bp_category_group
            FROM user_events ue
            LEFT JOIN business_profiles bp ON bp.id = ue.business_profile_id
            WHERE ue.id = ?
            """,
            (event_id,),
        ).fetchone()
        return dict(row) if row else None


def update_user_event(
    event_id: int,
    *,
    title: str,
    description: str | None,
    start_date: str,
    start_time: str | None,
    end_time: str | None,
    location_label: str | None,
    venue_name: str | None = None,
    address: str | None = None,
    tags_json: str | None = None,
    category: str | None = None,
    business_profile_id: str | None = None,
) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE user_events SET
              title = ?, description = ?, start_date = ?, start_time = ?, end_time = ?,
              location_label = ?, venue_name = ?, address = ?, tags = ?, category = ?,
              business_profile_id = COALESCE(?, business_profile_id),
              updated_at = ?
            WHERE id = ?
            """,
            (
                title,
                description,
                start_date,
                start_time,
                end_time,
                location_label,
                venue_name,
                address,
                tags_json,
                category,
                business_profile_id,
                now,
                event_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_user_event(event_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM user_events WHERE id = ?", (event_id,))
        conn.commit()
        return cur.rowcount > 0


def list_user_events_for_business(business_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM user_events WHERE business_id = ? ORDER BY start_date, id
            """,
            (business_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_all_user_events() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM user_events ORDER BY start_date, id"
        ).fetchall()
        return [dict(r) for r in rows]


def list_user_event_payloads_for_public() -> list[dict[str, Any]]:
    """Approved businesses only; shapes suitable for `normalize_item` (source=\"user\")."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ue.*, bp.name AS bp_name, bp.category_group AS bp_category_group
            FROM user_events ue
            INNER JOIN businesses b ON b.id = ue.business_id
            LEFT JOIN business_profiles bp ON bp.id = ue.business_profile_id
            WHERE b.role = 'business' AND b.status = 'approved'
            ORDER BY ue.start_date, ue.id
            """
        ).fetchall()
    return [map_user_event_row_to_item_payload(dict(r)) for r in rows]


def count_user_events_public() -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM user_events ue
            INNER JOIN businesses b ON b.id = ue.business_id
            WHERE b.role = 'business' AND b.status = 'approved'
            """
        ).fetchone()
        return int(row["n"]) if row else 0
