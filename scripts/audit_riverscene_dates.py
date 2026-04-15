"""One-off audit queries for RiverScene date quality (run from project root)."""
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
    rows = conn.execute(
        """
        SELECT id, payload_json FROM items
        WHERE type = 'event' AND source = 'riverscene'
          AND lower(json_extract(payload_json, '$.title')) LIKE '%altitude%'
        """,
    ).fetchall()
    print(f"Found {len(rows)} row(s) matching Altitude + riverscene\n")
    for r in rows:
        p = json.loads(r["payload_json"])
        print("id", r["id"])
        print("source_url", p.get("source_url"))
        print("title", p.get("title"))
        print("start_date", p.get("start_date"))
        print("end_date", p.get("end_date"))
        print("start_time", p.get("start_time"))
        print("end_time", p.get("end_time"))
        print("date_text", p.get("date_text"))
        print("date_raw", p.get("date_raw"))
        d = (p.get("description") or "")[:400]
        print("description[:400]", d)
        print("short_description", (p.get("short_description") or "")[:200])
        print("--- FULL PAYLOAD ---")
        print(json.dumps(p, indent=2))
        print()


if __name__ == "__main__":
    main()
