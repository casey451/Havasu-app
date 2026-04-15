"""
Clear suspicious RiverScene event dates (prefer missing over wrong).

Default: rows with start_date in SUSPICIOUS_DATES and title matching seasonal/holiday
keywords (likely the old full-page publish-date bug).

Usage (project root):
  py -3 scripts/cleanup_bad_event_dates.py
  py -3 scripts/cleanup_bad_event_dates.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "havasu.db"

_SEASONAL_TITLE = re.compile(
    r"\b("
    r"new\s+year|noon\s+year|year[\u2019']s\s+eve|nye|"
    r"christmas|x-?mas|thanksgiving|easter|halloween|valentine|"
    r"july\s*4|fourth\s+of\s+july|4th\s+of\s+july|st\.?\s*patrick"
    r")\b",
    re.I,
)

_DEFAULT_SUSPICIOUS = ("2026-04-14", "2026-04-15")


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matches but do not write DB",
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=DB,
        help="Path to SQLite DB",
    )
    args = ap.parse_args()

    suspicious = _DEFAULT_SUSPICIOUS
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, payload_json FROM items
        WHERE type = 'event' AND source = 'riverscene'
        """,
    ).fetchall()

    updated = 0
    for row in rows:
        p = json.loads(row["payload_json"])
        sd = str(p.get("start_date") or "").strip()
        if sd not in suspicious:
            continue
        title = str(p.get("title") or "")
        if not _SEASONAL_TITLE.search(title):
            continue
        print(f"clear id={row['id']} title={title[:70]!r} start_date={sd}")
        p["start_date"] = None
        p["end_date"] = None
        p["date_text"] = None
        if "date_raw" in p:
            p["date_raw"] = None
        p["riverscene_date_source"] = "cleaned_suspicious_seasonal"
        p["riverscene_date_confidence"] = "none"
        updated += 1
        if not args.dry_run:
            conn.execute(
                "UPDATE items SET payload_json = ? WHERE id = ?",
                (json.dumps(p, ensure_ascii=False), row["id"]),
            )
    if not args.dry_run:
        conn.commit()
    conn.close()
    print(f"Updated rows: {updated}" + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
