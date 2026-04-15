from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.item_identity import (
    compute_item_key,
    normalize_event_date_key,
    normalize_event_title_key,
)
from core.payload_merge import find_cross_source_event_candidate_id, merge_event_payloads
from core.storage_gates import should_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "havasu.db"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _payload_mirror_values(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Values for optional manual mirror columns (title, start_date, weekday)."""
    t = payload.get("title")
    out_t: str | None = t.strip() if isinstance(t, str) else None
    if out_t == "":
        out_t = None
    sd = payload.get("start_date")
    out_sd: str | None = None
    if sd is not None:
        s = str(sd).strip()
        if s:
            out_sd = s[:10] if len(s) >= 10 and s[4] == "-" else s
    w = payload.get("weekday")
    out_w = w.strip() if isinstance(w, str) and w.strip() else None
    return out_t, out_sd, out_w


def _items_all_column_names(conn: sqlite3.Connection) -> set[str]:
    """Includes generated columns (table_info alone may omit them on some SQLite builds)."""
    names: set[str] = set()
    try:
        for row in conn.execute("PRAGMA table_xinfo(items)"):
            names.add(str(row[1]))
    except sqlite3.OperationalError:
        for row in conn.execute("PRAGMA table_info(items)"):
            names.add(str(row[1]))
    return names


def _mirror_manual_flags(conn: sqlite3.Connection) -> tuple[bool, bool, bool]:
    """
    True if the column exists and is a plain (non-generated) column — must be set on upsert.
    """
    want = ("title", "start_date", "weekday")
    found = {n: False for n in want}
    try:
        for row in conn.execute("PRAGMA table_xinfo(items)"):
            name = row[1]
            if name not in found:
                continue
            hidden = int(row[6]) if len(row) > 6 else 0
            found[name] = hidden == 0
    except sqlite3.OperationalError:
        return (False, False, False)
    return (found["title"], found["start_date"], found["weekday"])


def _migrate_items_schema(conn: sqlite3.Connection) -> None:
    """item_key lifecycle, JSON mirror columns, dedupe, unique indexes (idempotent)."""
    try:
        cols = _items_all_column_names(conn)
    except sqlite3.OperationalError:
        return
    if not cols:
        return

    conn.execute("DROP INDEX IF EXISTS idx_items_item_key")
    conn.execute("DROP INDEX IF EXISTS idx_unique_recurring")
    conn.commit()

    if "item_key" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN item_key TEXT")
        conn.commit()

    mirror_specs = (
        ("title", "json_extract(payload_json, '$.title')"),
        ("start_date", "json_extract(payload_json, '$.start_date')"),
        ("weekday", "json_extract(payload_json, '$.weekday')"),
    )
    for col_name, expr in mirror_specs:
        all_cols = _items_all_column_names(conn)
        if col_name in all_cols:
            continue
        try:
            conn.execute(
                f"ALTER TABLE items ADD COLUMN {col_name} TEXT "
                f"GENERATED ALWAYS AS ({expr}) STORED"
            )
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            err = str(exc).lower()
            if "duplicate column name" in err:
                continue
            logger.warning(
                "items.%s: GENERATED column not available (%s); using manual TEXT + backfill",
                col_name,
                exc,
            )
            try:
                conn.execute(f"ALTER TABLE items ADD COLUMN {col_name} TEXT")
                conn.commit()
            except sqlite3.OperationalError as exc2:
                conn.rollback()
                if "duplicate column name" in str(exc2).lower():
                    continue
                raise

    mt, msd, mw = _mirror_manual_flags(conn)
    sets = []
    if mt:
        sets.append("title = json_extract(payload_json, '$.title')")
    if msd:
        sets.append("start_date = json_extract(payload_json, '$.start_date')")
    if mw:
        sets.append("weekday = json_extract(payload_json, '$.weekday')")
    if sets:
        conn.execute("UPDATE items SET " + ", ".join(sets))
        conn.commit()

    pragma_names = _items_all_column_names(conn)
    if "start_date" in pragma_names:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_start_date ON items(start_date)"
        )
        conn.commit()

    recur_dupes = conn.execute(
        """
        SELECT source,
               json_extract(payload_json, '$.title') AS t,
               json_extract(payload_json, '$.weekday') AS wd,
               json_extract(payload_json, '$.start_time') AS st,
               json_extract(payload_json, '$.end_time') AS et,
               MIN(id) AS keep_id
        FROM items
        WHERE type = 'recurring'
        GROUP BY 1, 2, 3, 4, 5
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for d in recur_dupes:
        conn.execute(
            """
            DELETE FROM items
            WHERE type = 'recurring'
              AND source = ?
              AND IFNULL(json_extract(payload_json, '$.title'), '') = IFNULL(?, '')
              AND IFNULL(json_extract(payload_json, '$.weekday'), '') = IFNULL(?, '')
              AND IFNULL(json_extract(payload_json, '$.start_time'), '') = IFNULL(?, '')
              AND IFNULL(json_extract(payload_json, '$.end_time'), '') = IFNULL(?, '')
              AND id != ?
            """,
            (
                d["source"],
                d["t"],
                d["wd"],
                d["st"],
                d["et"],
                int(d["keep_id"]),
            ),
        )
    conn.commit()

    for row in conn.execute("SELECT id, payload_json, source, type, source_url FROM items"):
        p = json.loads(row["payload_json"])
        p.setdefault("source", row["source"])
        p.setdefault("type", row["type"])
        p.setdefault("source_url", row["source_url"])
        k = compute_item_key(p)
        conn.execute("UPDATE items SET item_key = ? WHERE id = ?", (k, row["id"]))
    conn.commit()

    dupes = conn.execute(
        """
        SELECT item_key, MIN(id) AS keep_id
        FROM items
        WHERE item_key IS NOT NULL
        GROUP BY item_key
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for d in dupes:
        conn.execute(
            "DELETE FROM items WHERE item_key = ? AND id != ?",
            (d["item_key"], d["keep_id"]),
        )
    conn.commit()

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_item_key ON items(item_key)"
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_recurring
        ON items (
          source,
          json_extract(payload_json, '$.title'),
          json_extract(payload_json, '$.weekday'),
          json_extract(payload_json, '$.start_time'),
          json_extract(payload_json, '$.end_time')
        )
        WHERE type = 'recurring'
        """
    )
    conn.commit()


def _merge_cross_source_duplicate_event_rows(conn: sqlite3.Connection) -> int:
    """Merge pairs of cross-source duplicate events; returns rows deleted."""
    removed = 0
    while True:
        rows = conn.execute(
            "SELECT id, payload_json FROM items WHERE type = 'event' ORDER BY id"
        ).fetchall()
        if len(rows) < 2:
            break
        merged_pass = False
        for row in rows:
            rid = int(row["id"])
            payload = json.loads(row["payload_json"])
            cand = find_cross_source_event_candidate_id(conn, payload, exclude_id=rid)
            if cand is None or cand >= rid:
                continue
            keeper = cand
            loser = rid
            keep_row = conn.execute(
                "SELECT payload_json FROM items WHERE id = ?", (keeper,)
            ).fetchone()
            lose_row = conn.execute(
                "SELECT payload_json FROM items WHERE id = ?", (loser,)
            ).fetchone()
            if keep_row is None or lose_row is None:
                continue
            existing = json.loads(keep_row["payload_json"])
            incoming = json.loads(lose_row["payload_json"])
            merged = merge_event_payloads(existing, incoming)
            item_key = compute_item_key(merged)
            merged["item_key"] = item_key
            payload_json = json.dumps(merged, ensure_ascii=True)
            mv_t, mv_sd, mv_w = _payload_mirror_values(merged)
            mt, msd, mw = _mirror_manual_flags(conn)
            extra_set: list[str] = []
            extra_vals: list[Any] = []
            if mt:
                extra_set.append("title = ?")
                extra_vals.append(mv_t)
            if msd:
                extra_set.append("start_date = ?")
                extra_vals.append(mv_sd)
            if mw:
                extra_set.append("weekday = ?")
                extra_vals.append(mv_w)
            set_sql = (
                "UPDATE items SET source = ?, type = ?, source_url = ?, "
                "payload_json = ?, item_key = ?"
            )
            if extra_set:
                set_sql += ", " + ", ".join(extra_set)
            set_sql += " WHERE id = ?"
            conn.execute(
                set_sql,
                (
                    merged.get("source"),
                    merged.get("type"),
                    merged.get("source_url"),
                    payload_json,
                    item_key,
                    *extra_vals,
                    keeper,
                ),
            )
            conn.execute("DELETE FROM items WHERE id = ?", (loser,))
            conn.commit()
            removed += 1
            merged_pass = True
            break
        if not merged_pass:
            break
    return removed


def _bootstrap_admin_from_env(conn: sqlite3.Connection) -> None:
    """One-time admin row when env vars set and no admin exists."""
    import os

    from core.passwords import hash_password

    n = conn.execute("SELECT COUNT(*) AS c FROM businesses WHERE role = 'admin'").fetchone()
    if n and int(n["c"]) > 0:
        return
    email = os.environ.get("HAVASU_BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.environ.get("HAVASU_BOOTSTRAP_ADMIN_PASSWORD", "")
    name = os.environ.get("HAVASU_BOOTSTRAP_ADMIN_NAME", "Admin").strip() or "Admin"
    if not email or not password:
        return
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO businesses (email, password_hash, name, role, status, created_at, updated_at)
        VALUES (?, ?, ?, 'admin', 'approved', ?, ?)
        """,
        (email.lower(), hash_password(password), name, now, now),
    )
    conn.commit()
    logger.info("Bootstrapped admin account for email=%s", email)


def _migrate_user_events_venue_columns(conn: sqlite3.Connection) -> None:
    """Add venue_name / address to user_events when missing (older DBs)."""
    try:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(user_events)")}
    except sqlite3.OperationalError:
        return
    if not cols:
        return
    for col in ("venue_name", "address"):
        if col not in cols:
            conn.execute(f"ALTER TABLE user_events ADD COLUMN {col} TEXT")
    for col in ("tags", "category"):
        if col not in cols:
            conn.execute(f"ALTER TABLE user_events ADD COLUMN {col} TEXT")
    conn.commit()


def _migrate_business_profiles(conn: sqlite3.Connection) -> None:
    """Public `business_profiles` table + optional link on `user_events` (older DBs)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS business_profiles (
          id TEXT PRIMARY KEY,
          owner_business_id INTEGER NOT NULL UNIQUE,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          category TEXT NOT NULL,
          category_group TEXT NOT NULL,
          tags TEXT NOT NULL,
          phone TEXT,
          website TEXT,
          address TEXT,
          city TEXT NOT NULL DEFAULT 'Lake Havasu',
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          FOREIGN KEY (owner_business_id) REFERENCES businesses(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_profiles_owner ON business_profiles (owner_business_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_profiles_group ON business_profiles (category_group)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_business_profiles_active ON business_profiles (is_active)"
    )
    try:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(user_events)")}
    except sqlite3.OperationalError:
        conn.commit()
        return
    if cols and "business_profile_id" not in cols:
        conn.execute("ALTER TABLE user_events ADD COLUMN business_profile_id TEXT")
    conn.commit()


def _migrate_user_submissions_featured(conn: sqlite3.Connection) -> None:
    """Add featured controls to user_submissions for promoted listings."""
    try:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(user_submissions)")}
    except sqlite3.OperationalError:
        return
    if not cols:
        return
    if "is_featured" not in cols:
        conn.execute("ALTER TABLE user_submissions ADD COLUMN is_featured INTEGER NOT NULL DEFAULT 0")
    if "featured_until" not in cols:
        conn.execute("ALTER TABLE user_submissions ADD COLUMN featured_until TEXT")
    if "view_count" not in cols:
        conn.execute("ALTER TABLE user_submissions ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0")
    if "click_count" not in cols:
        conn.execute("ALTER TABLE user_submissions ADD COLUMN click_count INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _migrate_activities_and_slots(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          location TEXT NOT NULL,
          type TEXT NOT NULL CHECK (type IN ('event', 'schedule')),
          category TEXT NOT NULL DEFAULT 'events' CHECK (category IN ('kids', 'fitness', 'nightlife', 'events')),
          tags TEXT NOT NULL DEFAULT '[]',
          source TEXT NOT NULL DEFAULT 'user',
          status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('pending', 'approved', 'rejected')),
          view_count INTEGER NOT NULL DEFAULT 0,
          click_count INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    try:
        cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(activities)")}
    except sqlite3.OperationalError:
        cols = set()
    if cols and "category" not in cols:
        conn.execute(
            "ALTER TABLE activities ADD COLUMN category TEXT NOT NULL DEFAULT 'events'"
        )
    if cols and "tags" not in cols:
        conn.execute(
            "ALTER TABLE activities ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'"
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_status ON activities (status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_type ON activities (type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS time_slots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          activity_id INTEGER NOT NULL,
          start_time TEXT NOT NULL,
          end_time TEXT NOT NULL,
          day_of_week INTEGER,
          date TEXT,
          recurring INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
          CHECK (
            (date IS NOT NULL AND day_of_week IS NULL)
            OR (date IS NULL AND day_of_week IS NOT NULL)
          ),
          CHECK (day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)),
          CHECK (recurring IN (0, 1))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time_slots_activity ON time_slots (activity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time_slots_date ON time_slots (date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time_slots_weekday ON time_slots (day_of_week)")
    conn.commit()


def init_db() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema_sql)
        _migrate_user_events_venue_columns(conn)
        _migrate_business_profiles(conn)
        _migrate_user_submissions_featured(conn)
        _migrate_activities_and_slots(conn)
        _migrate_items_schema(conn)
        _merge_cross_source_duplicate_event_rows(conn)
        _bootstrap_admin_from_env(conn)


def run_pre_crawl_cleanup() -> None:
    """Remove known-bad rows (Step 5). Safe to run every crawl."""
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM items
            WHERE source = 'havasu_parks'
              AND source_url LIKE '%aquatic-center%'
            """
        )
        conn.execute(
            """
            DELETE FROM items
            WHERE source = 'golakehavasu'
              AND type = 'event'
              AND (
                source_url = 'https://www.golakehavasu.com/events/'
                OR source_url = 'https://www.golakehavasu.com/events'
                OR source_url = 'http://www.golakehavasu.com/events/'
                OR source_url = 'http://www.golakehavasu.com/events'
              )
            """
        )
        conn.commit()


def upsert_raw_page(
    *,
    url: str,
    source: str,
    status_code: int | None,
    html: str,
    content_sha256: str,
    fetched_at: str | None = None,
) -> int:
    fetched_at = fetched_at or utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO raw_pages (url, source, fetched_at, status_code, html, content_sha256)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                source=excluded.source,
                fetched_at=excluded.fetched_at,
                status_code=excluded.status_code,
                html=excluded.html,
                content_sha256=excluded.content_sha256
            """,
            (url, source, fetched_at, status_code, html, content_sha256),
        )
        row = conn.execute("SELECT id FROM raw_pages WHERE url = ?", (url,)).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert raw page for URL: {url}")
        return int(row["id"])


def delete_all_items_for_source(*, source: str) -> int:
    """Remove all item rows for a source (idempotent full re-ingest)."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM items WHERE source = ?", (source,))
        conn.commit()
        return cur.rowcount


def delete_items_with_source_urls(*, source: str, urls: tuple[str, ...]) -> int:
    """Delete rows matching exact source_url values (e.g. mistaken hub pages)."""
    if not urls:
        return 0
    n = 0
    with get_connection() as conn:
        for u in urls:
            cur = conn.execute(
                "DELETE FROM items WHERE source = ? AND source_url = ?",
                (source, u),
            )
            n += cur.rowcount
        conn.commit()
    return n


def delete_items_matching_source_url_pattern(*, source: str, url_substring: str) -> int:
    """Remove rows whose source_url contains url_substring (e.g. legacy crawler fragments)."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            DELETE FROM items
            WHERE source = ? AND source_url LIKE '%' || ? || '%'
            """,
            (source, url_substring),
        )
        conn.commit()
        return cur.rowcount


def upsert_item(
    *,
    payload: dict[str, Any],
    raw_page_id: int,
    updated_at: str | None = None,
) -> int | None:
    """
    Persist item with item_key + should_store gate.
    Returns None if should_store rejects (caller may count as skipped).
    """
    updated_at = updated_at or utc_now_iso()
    payload = dict(payload)
    source = payload.get("source", "")
    if not source or not isinstance(source, str) or not source.strip():
        raise ValueError("upsert_item requires non-empty payload['source']")

    item_key = compute_item_key(payload)
    payload["item_key"] = item_key

    if not should_store(payload):
        return None

    item_type = payload.get("type", "")
    source_url = payload.get("source_url", "")
    if not source_url or not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("upsert_item requires non-empty payload['source_url']")

    title = payload.get("title")
    weekday = payload.get("weekday")
    st = payload.get("start_time")
    et = payload.get("end_time")

    with get_connection() as conn:
        mt, msd, mw = _mirror_manual_flags(conn)
        row_key = conn.execute(
            "SELECT id FROM items WHERE item_key = ?", (item_key,)
        ).fetchone()
        row_evt = None
        if row_key is None and item_type == "event":
            tkn = normalize_event_title_key(title)
            sdk = normalize_event_date_key(payload.get("start_date"))
            if tkn and sdk:
                row_evt = conn.execute(
                    """
                    SELECT id FROM items
                    WHERE source = ?
                      AND type = 'event'
                      AND lower(trim(coalesce(json_extract(payload_json, '$.title'), ''))) = ?
                      AND substr(
                        trim(coalesce(json_extract(payload_json, '$.start_date'), '')),
                        1, 10
                      ) = ?
                    """,
                    (source, tkn, sdk),
                ).fetchone()

        row_cross = None
        if row_key is None and row_evt is None and item_type == "event":
            cid = find_cross_source_event_candidate_id(conn, payload)
            if cid is not None:
                row_cross = conn.execute(
                    "SELECT id FROM items WHERE id = ?", (cid,)
                ).fetchone()

        row_log = None
        if row_key is None and row_evt is None and row_cross is None and item_type == "recurring":
            row_log = conn.execute(
                """
                SELECT id FROM items
                WHERE source = ?
                  AND type = 'recurring'
                  AND IFNULL(json_extract(payload_json, '$.title'), '') = IFNULL(?, '')
                  AND IFNULL(json_extract(payload_json, '$.weekday'), '') = IFNULL(?, '')
                  AND IFNULL(json_extract(payload_json, '$.start_time'), '') = IFNULL(?, '')
                  AND IFNULL(json_extract(payload_json, '$.end_time'), '') = IFNULL(?, '')
                """,
                (source, title, weekday, st, et),
            ).fetchone()

        row_url = None
        if row_key is None and row_evt is None and row_cross is None and row_log is None:
            row_url = conn.execute(
                "SELECT id FROM items WHERE source_url = ?", (source_url,)
            ).fetchone()

        target = row_key or row_evt or row_cross or row_log or row_url
        if target is not None:
            tid = int(target["id"])
            cur = conn.execute(
                "SELECT payload_json FROM items WHERE id = ?", (tid,)
            ).fetchone()
            if cur is not None and item_type == "event":
                existing = json.loads(cur["payload_json"])
                payload = merge_event_payloads(existing, payload)
                item_key = compute_item_key(payload)
                payload["item_key"] = item_key
            mv_t, mv_sd, mv_w = _payload_mirror_values(payload)
            payload_json = json.dumps(payload, ensure_ascii=True)
            row_source = payload.get("source", source)
            row_type = payload.get("type", item_type)
            row_surl = payload.get("source_url", source_url)
            row_item_key = payload.get("item_key", item_key)
            # Free source_url for this canonical row (same URL may have pointed at a duplicate).
            conn.execute(
                "DELETE FROM items WHERE source_url = ? AND id != ?",
                (source_url, tid),
            )
            extra_set: list[str] = []
            extra_vals: list[Any] = []
            if mt:
                extra_set.append("title = ?")
                extra_vals.append(mv_t)
            if msd:
                extra_set.append("start_date = ?")
                extra_vals.append(mv_sd)
            if mw:
                extra_set.append("weekday = ?")
                extra_vals.append(mv_w)
            set_sql = """
                UPDATE items SET
                    source = ?,
                    type = ?,
                    source_url = ?,
                    payload_json = ?,
                    raw_page_id = ?,
                    updated_at = ?,
                    item_key = ?
            """
            if extra_set:
                set_sql += ", " + ", ".join(extra_set)
            set_sql += " WHERE id = ?"
            conn.execute(
                set_sql,
                (
                    row_source,
                    row_type,
                    row_surl,
                    payload_json,
                    raw_page_id,
                    updated_at,
                    row_item_key,
                    *extra_vals,
                    tid,
                ),
            )
            conn.commit()
            return tid

        mv_t, mv_sd, mv_w = _payload_mirror_values(payload)
        payload_json = json.dumps(payload, ensure_ascii=True)
        icols = [
            "source",
            "type",
            "source_url",
            "payload_json",
            "raw_page_id",
            "updated_at",
            "item_key",
        ]
        ivals: list[Any] = [
            source,
            item_type,
            source_url,
            payload_json,
            raw_page_id,
            updated_at,
            item_key,
        ]
        if mt:
            icols.append("title")
            ivals.append(mv_t)
        if msd:
            icols.append("start_date")
            ivals.append(mv_sd)
        if mw:
            icols.append("weekday")
            ivals.append(mv_w)
        ph = ", ".join("?" * len(icols))
        conn.execute(
            f"INSERT INTO items ({', '.join(icols)}) VALUES ({ph})",
            ivals,
        )
        conn.commit()
        row = conn.execute("SELECT id FROM items WHERE item_key = ?", (item_key,)).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert item for item_key: {item_key}")
        return int(row["id"])


def crawl_audit_summary() -> dict[str, Any]:
    """Post-crawl integrity snapshot (Step 8)."""
    with get_connection() as conn:
        by_source = {
            str(r["source"]): int(r["n"])
            for r in conn.execute(
                "SELECT source, COUNT(*) AS n FROM items GROUP BY source ORDER BY source"
            )
        }
        by_type = {
            str(r["type"]): int(r["n"])
            for r in conn.execute(
                "SELECT type, COUNT(*) AS n FROM items GROUP BY type ORDER BY type"
            )
        }
        dup_recurring = list(
            conn.execute(
                """
                SELECT source,
                       json_extract(payload_json, '$.title') AS t,
                       json_extract(payload_json, '$.weekday') AS wd,
                       json_extract(payload_json, '$.start_time') AS st,
                       json_extract(payload_json, '$.end_time') AS et,
                       COUNT(*) AS n
                FROM items
                WHERE type = 'recurring'
                GROUP BY 1, 2, 3, 4, 5
                HAVING COUNT(*) > 1
                """
            )
        )
        pragma_cols = _items_all_column_names(conn)
        if "start_date" in pragma_cols:
            missing_dates = conn.execute(
                """
                SELECT COUNT(*) AS n FROM items
                WHERE type = 'event'
                AND (
                  start_date IS NULL
                  OR trim(cast(start_date AS text)) = ''
                )
                """
            ).fetchone()["n"]
        else:
            missing_dates = conn.execute(
                """
                SELECT COUNT(*) AS n FROM items
                WHERE type = 'event'
                AND (
                  json_extract(payload_json, '$.start_date') IS NULL
                  OR json_extract(payload_json, '$.start_date') = ''
                )
                """
            ).fetchone()["n"]
        listing_events = conn.execute(
            """
            SELECT COUNT(*) AS n FROM items
            WHERE type = 'event'
            AND source = 'golakehavasu'
            AND (
              source_url = 'https://www.golakehavasu.com/events/'
              OR source_url = 'https://www.golakehavasu.com/events'
            )
            """
        ).fetchone()["n"]
        events_url_like_events = conn.execute(
            """
            SELECT COUNT(*) AS n FROM items
            WHERE type = 'event'
              AND source_url LIKE '%/events'
            """
        ).fetchone()["n"]

    return {
        "count_by_source": by_source,
        "count_by_type": by_type,
        "duplicate_recurring_groups": [dict(r) for r in dup_recurring],
        "events_missing_start_date": int(missing_dates),
        "golake_listing_hub_rows": int(listing_events),
        "events_source_url_like_pct_events": int(events_url_like_events),
    }


def list_items(
    *,
    item_type: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Load payloads from `items`, optionally filtered by type and/or source."""
    with get_connection() as conn:
        if item_type is None and source is None:
            rows = conn.execute(
                """
                SELECT id, payload_json
                FROM items
                ORDER BY updated_at DESC
                """,
            ).fetchall()
        elif item_type is not None and source is None:
            rows = conn.execute(
                """
                SELECT id, payload_json
                FROM items
                WHERE type = ?
                ORDER BY updated_at DESC
                """,
                (item_type,),
            ).fetchall()
        elif item_type is None and source is not None:
            rows = conn.execute(
                """
                SELECT id, payload_json
                FROM items
                WHERE source = ?
                ORDER BY updated_at DESC
                """,
                (source,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, payload_json
                FROM items
                WHERE type = ? AND source = ?
                ORDER BY updated_at DESC
                """,
                (item_type, source),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        p = json.loads(row["payload_json"])
        p["item_db_id"] = int(row["id"])
        out.append(p)
    return out


def get_item_payload_by_id(item_id: int) -> dict[str, Any] | None:
    """Single `items` row by primary key (crawler / stored payloads)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
    if row is None:
        return None
    p = json.loads(row["payload_json"])
    p["item_db_id"] = item_id
    return p


def list_events(source: str | None = None) -> list[dict[str, Any]]:
    """Calendar events only (`type='event'`)."""
    return list_items(item_type="event", source=source)


def count_events_by_source() -> dict[str, int]:
    """Row counts per source: crawler `items` (type=event) plus `user_events` as source ``user``."""
    from db.accounts import count_user_events_public

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT source, COUNT(*) AS n
            FROM items
            WHERE type = 'event'
            GROUP BY source
            ORDER BY source
            """
        ).fetchall()
    out: dict[str, int] = {str(r["source"]): int(r["n"]) for r in rows}
    nu = count_user_events_public()
    if nu:
        out["user"] = out.get("user", 0) + nu
    return dict(sorted(out.items()))
