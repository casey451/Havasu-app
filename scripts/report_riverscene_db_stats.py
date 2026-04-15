"""Summarize RiverScene rows in havasu.db (run from project root: py -3 scripts/report_riverscene_db_stats.py)."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "havasu.db"


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM items WHERE type='event' AND source='riverscene'"
    ).fetchone()["n"]
    null_sd = conn.execute(
        """
        SELECT COUNT(*) AS n FROM items
        WHERE type='event' AND source='riverscene'
          AND (
            json_extract(payload_json, '$.start_date') IS NULL
            OR trim(cast(json_extract(payload_json, '$.start_date') AS text)) = ''
          )
        """
    ).fetchone()["n"]
    print(f"riverscene event rows: {total}")
    print(f"  start_date null/empty: {null_sd}")
    rows = conn.execute(
        """
        SELECT json_extract(payload_json, '$.title') AS t,
               json_extract(payload_json, '$.start_date') AS sd,
               json_extract(payload_json, '$.riverscene_date_source') AS src,
               json_extract(payload_json, '$.riverscene_date_confidence') AS conf
        FROM items
        WHERE type='event' AND source='riverscene'
        ORDER BY random()
        LIMIT 10
        """
    ).fetchall()
    print("sample (random 10):")
    for r in rows:
        print(f"  - {r['sd']!s:12} | {r['src']!s:28} | {(r['t'] or '')[:60]}")
    conn.close()


if __name__ == "__main__":
    main()
