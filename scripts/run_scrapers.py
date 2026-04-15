from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.activities import ingest_activity
from db.database import init_db
from scripts.scrapers.aquatic_center import scrape_aquatic_center
from scripts.scrapers.bjj_academy import scrape_bjj_academy
from scripts.scrapers.trampoline_park import scrape_trampoline_park


def main() -> None:
    init_db()
    scraped = []
    scraped.extend(scrape_aquatic_center())
    scraped.extend(scrape_trampoline_park())
    scraped.extend(scrape_bjj_academy())
    ingested = 0
    for activity in scraped:
        ingest_activity(activity)
        ingested += 1
    print(f"scrapers_run=3")
    print(f"activities_ingested={ingested}")


if __name__ == "__main__":
    main()
