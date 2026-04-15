from __future__ import annotations

import json
import sqlite3

import pytest


def _insert_raw_page(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        INSERT INTO raw_pages (url, source, fetched_at, status_code, html, content_sha256)
        VALUES ('https://example.com/raw', 'test', '2026-01-01T00:00:00+00:00', 200, '<html/>', 'x')
        """
    )
    conn.commit()
    row = conn.execute("SELECT id FROM raw_pages WHERE url = ?", ("https://example.com/raw",)).fetchone()
    assert row is not None
    return int(row[0])


def test_no_events_missing_start_date(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE type = 'event'
            AND (
              json_extract(payload_json, '$.start_date') IS NULL
              OR json_extract(payload_json, '$.start_date') = ''
            )
            """
        ).fetchone()[0]
    assert int(n) == 0


def test_no_duplicate_recurring_groups(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT source, json_extract(payload_json, '$.title') AS t,
                   json_extract(payload_json, '$.weekday') AS wd,
                   json_extract(payload_json, '$.start_time') AS st,
                   json_extract(payload_json, '$.end_time') AS et,
                   COUNT(*) AS n
            FROM items
            WHERE type = 'recurring'
            GROUP BY 1, 2, 3, 4, 5
            HAVING COUNT(*) > 1
            """
        ).fetchall()
    assert len(rows) == 0


def test_no_listing_events_url_pattern(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE type = 'event'
            AND source_url LIKE '%/events'
            """
        ).fetchone()[0]
    assert int(n) == 0


def test_recurring_logical_dedupe_second_url_updates_same_row(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        rid = _insert_raw_page(conn)
    base = {
        "source": "havasu_parks",
        "type": "recurring",
        "title": "Lap Swim",
        "weekday": "Monday",
        "start_time": "06:00",
        "end_time": "08:00",
        "source_url": "https://parks.example/o/page#slot-a",
        "location_label": "Pool",
    }
    id1 = dbm.upsert_item(payload=dict(base), raw_page_id=rid)
    assert id1 is not None
    id2 = dbm.upsert_item(
        payload={**base, "source_url": "https://parks.example/o/page#slot-b"},
        raw_page_id=rid,
    )
    assert id2 == id1
    with dbm.get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM items WHERE type = 'recurring'").fetchone()[0]
        assert int(n) == 1


def test_should_store_blocks_short_title(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        rid = _insert_raw_page(conn)
    out = dbm.upsert_item(
        payload={
            "source": "golakehavasu",
            "type": "event",
            "title": "ab",
            "start_date": "2026-06-01",
            "source_url": "https://www.golakehavasu.com/events/x",
        },
        raw_page_id=rid,
    )
    assert out is None


def test_event_dedupe_same_title_and_date_merges_urls(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        rid = _insert_raw_page(conn)
    base = {
        "source": "riverscene",
        "type": "event",
        "title": "Duplicate Title Check",
        "start_date": "2026-08-01",
        "start_time": "10:00",
        "end_time": "12:00",
        "source_url": "https://riverscenemagazine.com/events/first-slug/",
    }
    id1 = dbm.upsert_item(payload=dict(base), raw_page_id=rid)
    assert id1 is not None
    id2 = dbm.upsert_item(
        payload={
            **base,
            "source_url": "https://riverscenemagazine.com/events/second-slug/",
        },
        raw_page_id=rid,
    )
    assert id2 == id1
    with dbm.get_connection() as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE source = 'riverscene' AND type = 'event'
              AND lower(trim(coalesce(json_extract(payload_json, '$.title'), ''))) = 'duplicate title check'
              AND substr(trim(coalesce(json_extract(payload_json, '$.start_date'), '')), 1, 10) = '2026-08-01'
            """
        ).fetchone()[0]
        assert int(n) == 1


def test_should_store_riverscene_requires_start_and_end_time(fresh_db: object) -> None:
    from core.storage_gates import should_store

    assert not should_store(
        {
            "source": "riverscene",
            "type": "event",
            "title": "Has date no time",
            "start_date": "2026-01-02",
            "start_time": None,
            "end_time": None,
        }
    )
    assert should_store(
        {
            "source": "riverscene",
            "type": "event",
            "title": "Has date and times",
            "start_date": "2026-01-02",
            "start_time": "09:00",
            "end_time": "11:00",
        }
    )
    assert should_store(
        {
            "source": "golakehavasu",
            "type": "event",
            "title": "GoLake no clock fields ok",
            "start_date": "2026-01-02",
            "start_time": None,
            "end_time": None,
        }
    )


def test_db_check_rejects_event_without_start_date(fresh_db: object) -> None:
    import db.database as dbm

    with dbm.get_connection() as conn:
        rid = _insert_raw_page(conn)
    payload = {
        "source": "golakehavasu",
        "type": "event",
        "title": "Valid title here",
        "start_date": None,
        "source_url": "https://www.golakehavasu.com/events/bad",
    }
    bad_json = json.dumps(payload)
    with dbm.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO items (source, type, source_url, payload_json, raw_page_id, updated_at, item_key)
                VALUES ('golakehavasu', 'event', ?, ?, ?, '2026-01-01T00:00:00+00:00', 'manual-key-bad-event')
                """,
                (payload["source_url"], bad_json, rid),
            )
