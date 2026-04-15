# Lake Havasu Discovery Backend (Milestone 1)

Modular Python backend pipeline for Go Lake Havasu events:

1. Discover event URLs
2. Fetch event HTML and store raw pages
3. Parse event data
4. Normalize to a shared payload shape
5. Store normalized records in SQLite
6. Serve events via FastAPI

## Tech stack

- Python
- FastAPI
- SQLite
- httpx
- BeautifulSoup

## Project layout

- `crawler/sources/golakehavasu/discover.py`
- `crawler/sources/golakehavasu/fetch.py`
- `crawler/sources/golakehavasu/parse_events.py`
- `crawler/sources/golakehavasu/normalize.py`
- `core/http.py`
- `core/storage.py`
- `core/models.py`
- `db/schema.sql`
- `db/database.py`
- `jobs/run_crawler.py`
- `api/main.py`

## Run locally

1. Create and activate virtual environment:
   - PowerShell:
     - `python -m venv .venv`
     - `.\\.venv\\Scripts\\Activate.ps1`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run crawler job (creates/initializes DB automatically):
   - `python jobs/run_crawler.py`
4. Run API server:
   - `uvicorn api.main:app --reload`
5. Read events:
   - `GET http://127.0.0.1:8000/events`

## Notes

- Raw HTML is always stored in `raw_pages`.
- Normalized event payloads are stored in `items.payload_json`.
- Current source is only `golakehavasu` (milestone 1 scope).
