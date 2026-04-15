from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from db.database import get_connection, utc_now_iso

SubmissionStatus = Literal["pending", "approved", "rejected"]


def create_submission(
    *,
    title: str,
    description: str,
    tags: list[str],
    category: str,
    start_date: str | None,
    location: str,
) -> str:
    sid = f"s-{uuid.uuid4().hex[:16]}"
    now = utc_now_iso()
    tags_json = json.dumps(tags)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_submissions (
              id, title, description, tags, category, start_date, location,
              source, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'user', 'pending', ?, ?)
            """,
            (sid, title, description, tags_json, category, start_date, location, now, now),
        )
        conn.commit()
    return sid


def find_duplicate_submission_id(*, normalized_title: str, start_date: str) -> str | None:
    """Duplicate = same normalized title + same start_date among pending/approved rows."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM user_submissions
            WHERE lower(trim(title)) = ?
              AND trim(COALESCE(start_date, '')) = ?
              AND status IN ('pending', 'approved')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (normalized_title, start_date.strip()),
        ).fetchone()
    if row is None:
        return None
    return str(row["id"])


def list_pending_submissions() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, tags, category, start_date, location, source, status, created_at,
                   view_count, click_count
            FROM user_submissions
            WHERE status = 'pending'
            ORDER BY created_at DESC
            """
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(str(d.get("tags") or "[]"))
        except json.JSONDecodeError:
            d["tags"] = []
        views = int(d.get("view_count") or 0)
        clicks = int(d.get("click_count") or 0)
        d["ctr"] = round((clicks / views), 4) if views > 0 else 0.0
        out.append(d)
    return out


def list_submissions(status: SubmissionStatus) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, tags, category, start_date, location, source, status, created_at,
                   is_featured, featured_until, view_count, click_count
            FROM user_submissions
            WHERE status = ?
            ORDER BY created_at DESC
            """,
            (status,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(str(d.get("tags") or "[]"))
        except json.JSONDecodeError:
            d["tags"] = []
        views = int(d.get("view_count") or 0)
        clicks = int(d.get("click_count") or 0)
        d["ctr"] = round((clicks / views), 4) if views > 0 else 0.0
        out.append(d)
    return out


def update_submission_status(submission_id: str, status: SubmissionStatus) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE user_submissions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, submission_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_submission(submission_id: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM user_submissions WHERE id = ?", (submission_id,))
        conn.commit()
        return cur.rowcount > 0


def list_approved_submission_payloads() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description, tags, category, start_date, location, source, status,
                   is_featured, featured_until, view_count, click_count
            FROM user_submissions
            WHERE status = 'approved'
            ORDER BY updated_at DESC
            """
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        try:
            tags = json.loads(str(d.get("tags") or "[]"))
        except json.JSONDecodeError:
            tags = []
        start = str(d.get("start_date") or "")
        payload = {
            "event_ref": str(d.get("id") or ""),
            "title": str(d.get("title") or ""),
            "type": "event",
            "start_date": start,
            "end_date": start,
            "weekday": "",
            "start_time": "",
            "end_time": "",
            "location_label": str(d.get("location") or ""),
            "source": "user",
            "source_url": f"/submit/{d.get('id')}",
            "description": str(d.get("description") or ""),
            "tags": tags if isinstance(tags, list) else [],
            "category": str(d.get("category") or ""),
            "trust_score": 0.8,
            "is_featured": bool(int(d.get("is_featured") or 0)),
            "featured_until": str(d.get("featured_until") or ""),
            "view_count": int(d.get("view_count") or 0),
            "click_count": int(d.get("click_count") or 0),
        }
        out.append(payload)
    return out


def set_submission_featured(submission_id: str, *, days: int) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM user_submissions WHERE id = ? AND status = 'approved'",
            (submission_id,),
        ).fetchone()
        if row is None:
            return False
        cur = conn.execute(
            """
            UPDATE user_submissions
            SET is_featured = 1,
                featured_until = datetime('now', ?),
                updated_at = ?
            WHERE id = ?
            """,
            (f"+{max(1, days)} days", now, submission_id),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_submission_featured(submission_id: str) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE user_submissions
            SET is_featured = 0, featured_until = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now, submission_id),
        )
        conn.commit()
        return cur.rowcount > 0


def increment_submission_view(submission_id: str) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE user_submissions
            SET view_count = COALESCE(view_count, 0) + 1,
                updated_at = ?
            WHERE id = ? AND status = 'approved'
            """,
            (now, submission_id),
        )
        conn.commit()
        return cur.rowcount > 0


def increment_submission_click(submission_id: str) -> bool:
    now = utc_now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE user_submissions
            SET click_count = COALESCE(click_count, 0) + 1,
                updated_at = ?
            WHERE id = ? AND status = 'approved'
            """,
            (now, submission_id),
        )
        conn.commit()
        return cur.rowcount > 0


def list_notifications_feed(limit: int = 20) -> list[dict[str, Any]]:
    lim = max(1, min(50, int(limit)))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, category, start_date, source, is_featured, featured_until, created_at, updated_at
            FROM user_submissions
            WHERE status = 'approved'
            ORDER BY datetime(updated_at) DESC, rowid DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        out.append(
            {
                "id": str(d.get("id") or ""),
                "event_ref": str(d.get("id") or ""),
                "title": str(d.get("title") or ""),
                "type": "event",
                "start_date": str(d.get("start_date") or ""),
                "source": str(d.get("source") or "user"),
                "is_featured": bool(int(d.get("is_featured") or 0)),
                "featured_until": str(d.get("featured_until") or ""),
                "created_at": str(d.get("created_at") or ""),
                "updated_at": str(d.get("updated_at") or ""),
            }
        )
    return out
