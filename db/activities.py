from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import sqlite3

from db.database import get_connection, utc_now_iso


@dataclass(frozen=True)
class SlotInput:
    start_time: str
    end_time: str
    day_of_week: int | None = None
    date: str | None = None
    recurring: bool = False


@dataclass(frozen=True)
class ActivityInput:
    title: str
    location: str
    activity_type: str
    category: str
    tags: list[str]
    time_slots: list[SlotInput]
    source: str = "scraped"
    status: str = "approved"
    description: str = ""


def _normalize_category(value: str) -> str:
    cat = (value or "").strip().lower()
    return cat if cat in {"kids", "fitness", "nightlife", "events"} else "events"


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not isinstance(tags, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        s = str(t).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:20]


def upsert_activity(
    *,
    title: str,
    location: str,
    activity_type: str,
    status: str = "approved",
    source: str = "seed",
    description: str = "",
    category: str = "events",
    tags: list[str] | None = None,
) -> str:
    now = utc_now_iso()
    category_norm = _normalize_category(category)
    tags_norm = _normalize_tags(tags)
    tags_json = json.dumps(tags_norm)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM activities
            WHERE lower(trim(title)) = lower(trim(?))
              AND lower(trim(location)) = lower(trim(?))
              AND type = ?
            LIMIT 1
            """,
            (title, location, activity_type),
        ).fetchone()
        if row is not None:
            aid = str(row["id"])
            conn.execute(
                """
                UPDATE activities
                SET description = ?, category = ?, tags = ?, status = ?, source = ?, updated_at = ?
                WHERE id = ?
                """,
                (description, category_norm, tags_json, status, source, now, aid),
            )
            conn.commit()
            return aid

        conn.execute(
            """
            INSERT INTO activities (
              title, description, location, type, category, tags, source, status,
              view_count, click_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (title, description, location, activity_type, category_norm, tags_json, source, status, now, now),
        )
        rid = conn.execute("SELECT last_insert_rowid() AS rid").fetchone()
        conn.commit()
        return f"a-{int(rid['rid'])}"


def ingest_activity(activity_data: ActivityInput) -> str:
    activity_id = upsert_activity(
        title=activity_data.title,
        location=activity_data.location,
        activity_type=activity_data.activity_type,
        source=activity_data.source,
        status=activity_data.status,
        description=activity_data.description,
        category=activity_data.category,
        tags=activity_data.tags,
    )
    replace_time_slots(activity_id, activity_data.time_slots)
    return activity_id


def replace_time_slots(activity_id: str, slots: list[SlotInput]) -> None:
    aid = _parse_activity_id(activity_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM time_slots WHERE activity_id = ?", (aid,))
        for s in slots:
            conn.execute(
                """
                INSERT INTO time_slots (
                  activity_id, start_time, end_time, day_of_week, date, recurring, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    s.start_time,
                    s.end_time,
                    s.day_of_week,
                    s.date,
                    1 if s.recurring else 0,
                    utc_now_iso(),
                ),
            )
        conn.commit()


def increment_activity_view(activity_id: str) -> bool:
    aid = _parse_activity_id_safe(activity_id)
    if aid is None:
        return False
    with get_connection() as conn:
        try:
            cur = conn.execute(
                """
                UPDATE activities
                SET view_count = COALESCE(view_count, 0) + 1,
                    updated_at = ?
                WHERE id = ? AND status = 'approved'
                """,
                (utc_now_iso(), aid),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.OperationalError:
            return False


def increment_activity_click(activity_id: str) -> bool:
    aid = _parse_activity_id_safe(activity_id)
    if aid is None:
        return False
    with get_connection() as conn:
        try:
            cur = conn.execute(
                """
                UPDATE activities
                SET click_count = COALESCE(click_count, 0) + 1,
                    updated_at = ?
                WHERE id = ? AND status = 'approved'
                """,
                (utc_now_iso(), aid),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.OperationalError:
            return False


def list_expanded_slot_payloads(*, days_back: int = 2, days_ahead: int = 14) -> list[dict[str, Any]]:
    today = date.today()
    start = today - timedelta(days=max(0, days_back))
    end = today + timedelta(days=max(1, days_ahead))
    with get_connection() as conn:
        try:
            rows = conn.execute(
                """
                SELECT
                  a.id AS activity_id,
                  a.title,
                  a.location,
                  a.type AS activity_type,
                  a.category,
                  a.tags,
                  a.view_count,
                  a.click_count,
                  ts.id AS slot_id,
                  ts.start_time,
                  ts.end_time,
                  ts.day_of_week,
                  ts.date,
                  ts.recurring
                FROM activities a
                JOIN time_slots ts ON ts.activity_id = a.id
                WHERE a.status = 'approved'
                ORDER BY a.id, ts.id
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    out: list[dict[str, Any]] = []
    for r in rows:
        activity_id = f"a-{int(r['activity_id'])}"
        slot_date_values = _expand_slot_dates(
            recurring=bool(int(r["recurring"] or 0)),
            explicit_date=str(r["date"] or "").strip() or None,
            day_of_week=r["day_of_week"],
            window_start=start,
            window_end=end,
        )
        for slot_day in slot_date_values:
            start_iso = f"{slot_day.isoformat()}T{str(r['start_time'])}"
            end_iso = f"{slot_day.isoformat()}T{str(r['end_time'])}"
            raw_tags = str(r["tags"] or "[]")
            try:
                tags = json.loads(raw_tags)
            except json.JSONDecodeError:
                tags = []
            if not isinstance(tags, list):
                tags = []
            out.append(
                {
                    "id": activity_id,
                    "event_ref": activity_id,
                    "activity_id": activity_id,
                    "slot_id": int(r["slot_id"]),
                    "title": str(r["title"] or ""),
                    "type": "event",
                    "start_date": start_iso,
                    "end_date": end_iso,
                    "start_time": str(r["start_time"] or ""),
                    "end_time": str(r["end_time"] or ""),
                    "location": str(r["location"] or ""),
                    "location_label": str(r["location"] or ""),
                    "source": "activity",
                    "source_url": f"/activities/{activity_id}",
                    "category": str(r["category"] or "events"),
                    "tags": tags,
                    "view_count": int(r["view_count"] or 0),
                    "click_count": int(r["click_count"] or 0),
                }
            )
    return out


def list_pending_activities() -> list[dict[str, Any]]:
    with get_connection() as conn:
        try:
            rows = conn.execute(
                """
                SELECT
                  a.id,
                  a.title,
                  a.location,
                  a.category,
                  a.tags,
                  a.source,
                  a.status,
                  MIN(COALESCE(ts.date, '')) AS first_date,
                  MIN(COALESCE(ts.start_time, '')) AS first_time
                FROM activities a
                LEFT JOIN time_slots ts ON ts.activity_id = a.id
                WHERE a.status = 'pending'
                GROUP BY a.id, a.title, a.location, a.category, a.tags, a.source, a.status
                ORDER BY a.created_at DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            tags = json.loads(str(r["tags"] or "[]"))
        except json.JSONDecodeError:
            tags = []
        start = str(r["first_date"] or "").strip()
        st = str(r["first_time"] or "").strip()
        start_date = f"{start}T{st}" if start and st else start
        out.append(
            {
                "id": f"a-{int(r['id'])}",
                "title": str(r["title"] or ""),
                "location": str(r["location"] or ""),
                "category": str(r["category"] or "events"),
                "tags": tags if isinstance(tags, list) else [],
                "source": str(r["source"] or "user"),
                "status": str(r["status"] or "pending"),
                "start_date": start_date,
            }
        )
    return out


def set_activity_status(activity_id: str, status: str) -> bool:
    aid = _parse_activity_id_safe(activity_id)
    if aid is None:
        return False
    now = utc_now_iso()
    with get_connection() as conn:
        try:
            cur = conn.execute(
                "UPDATE activities SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, aid),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.OperationalError:
            return False


def delete_activity(activity_id: str) -> bool:
    aid = _parse_activity_id_safe(activity_id)
    if aid is None:
        return False
    with get_connection() as conn:
        try:
            cur = conn.execute("DELETE FROM activities WHERE id = ?", (aid,))
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.OperationalError:
            return False


def _normalize_ai_query(value: str) -> str:
    # Keep normalization stable so click learning compares equivalent queries.
    q = (value or "").lower().strip()
    q = re.sub(r"[^a-z0-9\s]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def tokenize(text: str) -> list[str]:
    q = _normalize_ai_query(text)
    if not q:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for token in q.split(" "):
        if len(token) < 3 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def log_ai_interaction(query: str, returned_ids: list[str]) -> str:
    interaction_id = f"ai-{uuid.uuid4().hex[:16]}"
    q = _normalize_ai_query(query)
    if not q:
        return ""
    ids = [str(i).strip() for i in returned_ids if str(i).strip()]
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO ai_interactions (id, query, returned_ids, clicked_id)
                VALUES (?, ?, ?, NULL)
                """,
                (interaction_id, q, json.dumps(ids, ensure_ascii=True)),
            )
            conn.commit()
        except sqlite3.OperationalError:
            return ""
    return interaction_id


def record_ai_click(query: str, clicked_id: str) -> bool:
    q = _normalize_ai_query(query)
    cid = (clicked_id or "").strip()
    if not q or not cid:
        return False
    with get_connection() as conn:
        try:
            row = conn.execute(
                """
                SELECT id
                FROM ai_interactions
                WHERE query = ? AND clicked_id IS NULL
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (q,),
            ).fetchone()
            if row is None:
                return False
            cur = conn.execute(
                "UPDATE ai_interactions SET clicked_id = ? WHERE id = ?",
                (cid, str(row["id"])),
            )
            conn.commit()
            return cur.rowcount > 0
        except sqlite3.OperationalError:
            return False


def get_ai_clicked_weights(query: str) -> dict[str, float]:
    q_tokens = tokenize(query)
    if not q_tokens:
        return {}
    q_set = set(q_tokens)
    with get_connection() as conn:
        try:
            rows = conn.execute(
                """
                SELECT clicked_id, query
                FROM ai_interactions
                WHERE clicked_id IS NOT NULL
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 500
                """,
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    out: dict[str, float] = {}
    for r in rows:
        cid = str(r["clicked_id"] or "").strip()
        if not cid:
            continue
        past_tokens = tokenize(str(r["query"] or ""))
        if not past_tokens:
            continue
        overlap = len(q_set.intersection(set(past_tokens)))
        if overlap <= 0:
            continue
        match_weight = overlap / float(len(q_tokens))
        out[cid] = out.get(cid, 0.0) + match_weight
    return out


def get_event_click_counts() -> dict[str, int]:
    with get_connection() as conn:
        try:
            rows = conn.execute(
                """
                SELECT clicked_id, COUNT(*) AS c
                FROM ai_interactions
                WHERE clicked_id IS NOT NULL
                GROUP BY clicked_id
                ORDER BY c DESC
                LIMIT 1000
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    out: dict[str, int] = {}
    for r in rows:
        cid = str(r["clicked_id"] or "").strip()
        if not cid:
            continue
        out[cid] = int(r["c"] or 0)
    return out


def build_event_embedding_text(event: dict[str, Any]) -> str:
    title = str(event.get("title") or "").strip()
    description = str(event.get("description") or "").strip()
    category = str(event.get("category") or "").strip()
    tags = event.get("tags") if isinstance(event.get("tags"), list) else []
    intent_tags = event.get("intent_tags") if isinstance(event.get("intent_tags"), list) else []
    tags_text = " ".join(str(t).strip() for t in tags if str(t).strip())
    intent_text = " ".join(str(t).strip() for t in intent_tags if str(t).strip())
    return " ".join(part for part in [title, description, category, tags_text, intent_text] if part).strip()


def _expand_slot_dates(
    *,
    recurring: bool,
    explicit_date: str | None,
    day_of_week: Any,
    window_start: date,
    window_end: date,
) -> list[date]:
    if explicit_date:
        try:
            d = date.fromisoformat(explicit_date[:10])
            if window_start <= d <= window_end:
                return [d]
        except ValueError:
            return []
        return []

    if not recurring:
        return []

    try:
        dow = int(day_of_week)
    except (TypeError, ValueError):
        return []
    if dow < 0 or dow > 6:
        return []

    results: list[date] = []
    cur = window_start
    while cur <= window_end:
        if cur.weekday() == dow:
            results.append(cur)
        cur += timedelta(days=1)
    return results


def _parse_activity_id(activity_id: str) -> int:
    aid = _parse_activity_id_safe(activity_id)
    if aid is None:
        raise ValueError("Invalid activity id")
    return aid


def _parse_activity_id_safe(activity_id: str) -> int | None:
    raw = (activity_id or "").strip()
    if raw.startswith("a-"):
        raw = raw[2:]
    if not raw.isdigit():
        return None
    return int(raw)
