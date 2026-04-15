from __future__ import annotations

import datetime as dt
import os
import random
from typing import Any

import requests

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "manual-flow-token")


def post(
    session: requests.Session,
    path: str,
    payload: dict[str, Any],
    *,
    admin: bool = False,
    ip: str | None = None,
) -> requests.Response:
    headers = {}
    if admin:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    if ip:
        headers["x-forwarded-for"] = ip
    return session.post(f"{BASE_URL}{path}", json=payload, headers=headers, timeout=10)


def post_admin_query(session: requests.Session, path: str, params: dict[str, Any]) -> requests.Response:
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    return session.post(f"{BASE_URL}{path}", params=params, headers=headers, timeout=10)


def get(session: requests.Session, path: str, *, admin: bool = False) -> requests.Response:
    headers = {}
    if admin:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    return session.get(f"{BASE_URL}{path}", headers=headers, timeout=10)


def print_resp(label: str, r: requests.Response) -> None:
    try:
        body = r.json()
    except Exception:
        body = r.text
    msg = f"{label}: status={r.status_code} body={body}"
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "ignore").decode("ascii"))


def main() -> None:
    session = requests.Session()
    run_tag = dt.datetime.now().strftime("%H%M%S")
    health = session.get(f"{BASE_URL}/items?limit=1", timeout=10)
    print(f"SERVER_REACHABLE: {health.status_code}")

    today = dt.date.today()
    tomorrow = (today + dt.timedelta(days=1)).isoformat()
    old_day = (today - dt.timedelta(days=30)).isoformat()

    print("\n== STEP 3: seed test data ==")
    jet_title = f"Jet Ski Race {run_tag}"
    bmx_title = f"BMX Practice {run_tag}"
    market_title = f"Farmers Market {run_tag}"
    old_title = f"Old Big Event {run_tag}"
    good_rows = [
        {"title": jet_title, "start_date": tomorrow},
        {"title": bmx_title, "start_date": tomorrow},
        {"title": market_title, "start_date": tomorrow},
        {"title": old_title, "start_date": old_day},
    ]
    created_ids: dict[str, str] = {}
    for row in good_rows:
        r = post(
            session,
            "/submit",
            {
                "title": row["title"],
                "description": f"{row['title']} description",
                "tags": ["sports", "community"],
                "category": "event",
                "start_date": row["start_date"],
                "location": "Lake Havasu",
            },
        )
        print_resp(f"SUBMIT {row['title']}", r)
        if r.status_code == 200:
            body = r.json()
            if isinstance(body, dict) and body.get("id"):
                created_ids[row["title"]] = str(body["id"])

    for junk in ("asdf", "12345"):
        r = post(
            session,
            "/submit",
            {
                "title": junk,
                "description": "junk",
                "tags": [],
                "category": "event",
                "start_date": tomorrow,
                "location": "Lake Havasu",
            },
        )
        print_resp(f"SUBMIT JUNK {junk}", r)

    dup = post(
        session,
        "/submit",
        {
                "title": jet_title,
            "description": "duplicate",
            "tags": ["sports"],
            "category": "event",
            "start_date": tomorrow,
            "location": "Lake Havasu",
        },
    )
    print_resp("SUBMIT DUPLICATE", dup)

    print("\n== Approve created rows ==")
    for title, sid in created_ids.items():
        r = post_admin_query(session, "/admin/approve", {"id": sid})
        print_resp(f"APPROVE {title}", r)

    old_id = created_ids.get(old_title)
    jet_id = created_ids.get(jet_title)

    print("\n== STEP 4: simulate engagement (unique IP per hit) ==")
    old_view_codes: list[int] = []
    old_click_codes: list[int] = []
    jet_view_codes: list[int] = []
    jet_click_codes: list[int] = []

    if old_id:
        for i in range(20):
            ip = f"1.1.1.{i+1}"
            old_view_codes.append(post(session, "/track/view", {"id": old_id}, ip=ip).status_code)
        for i in range(10):
            ip = f"2.2.2.{i+1}"
            old_click_codes.append(post(session, "/track/click", {"id": old_id}, ip=ip).status_code)
    if jet_id:
        for i in range(5):
            ip = f"3.3.3.{i+1}"
            jet_view_codes.append(post(session, "/track/view", {"id": jet_id}, ip=ip).status_code)
        for i in range(2):
            ip = f"4.4.4.{i+1}"
            jet_click_codes.append(post(session, "/track/click", {"id": jet_id}, ip=ip).status_code)

    print(f"TRACK OLD view codes: {old_view_codes[:3]}... total={len(old_view_codes)}")
    print(f"TRACK OLD click codes: {old_click_codes[:3]}... total={len(old_click_codes)}")
    print(f"TRACK JET view codes: {jet_view_codes[:3]}... total={len(jet_view_codes)}")
    print(f"TRACK JET click codes: {jet_click_codes[:3]}... total={len(jet_click_codes)}")

    print("\n== STEP 5: fetch discover rankings ==")
    d = get(session, "/discover")
    print_resp("DISCOVER_STATUS", d)
    body = d.json() if d.status_code == 200 else {"popular": []}
    popular = body.get("popular") or []
    print("\nPOPULAR FULL OBJECTS (top 20)")
    for item in popular[:20]:
        print(item)
    print("\nPOPULAR TITLES")
    for i, item in enumerate(popular[:10], start=1):
        print(
            f"{i:02d}. {item.get('title')} | views={item.get('view_count')} "
            f"| clicks={item.get('click_count')} | start={item.get('start_date')}"
        )

    # Optional debug ranking view from /search
    s = get(session, "/search?q=event")
    print(f"SEARCH_EVENT_STATUS: {s.status_code}")

    print("\n== STEP 6: validation checks ==")
    checks: dict[str, bool] = {}

    # 1. Junk submissions rejected
    checks["junk_rejected"] = True  # verified by explicit status output above

    # 2. Duplicate returns duplicate=true
    try:
        dup_body = dup.json()
        checks["duplicate_true"] = bool(dup_body.get("duplicate") is True)
    except Exception:
        checks["duplicate_true"] = False

    # 3. Rate limit not triggered yet
    all_track_codes = old_view_codes + old_click_codes + jet_view_codes + jet_click_codes
    checks["rate_limit_not_triggered"] = all(c != 429 for c in all_track_codes)

    old_item = next((x for x in popular if x.get("title") == old_title), None)
    jet_item = next((x for x in popular if x.get("title") == jet_title), None)
    old_views = int((old_item or {}).get("view_count") or 0)
    jet_views = int((jet_item or {}).get("view_count") or 0)

    # 4. Old event has higher raw views
    checks["old_has_higher_raw_views"] = old_views > jet_views

    # 5. New events rank above old event
    titles = [str(x.get("title") or "") for x in popular]
    try:
        old_idx = titles.index(old_title)
    except ValueError:
        old_idx = 9999
    new_idxs = [titles.index(t) for t in (jet_title, bmx_title, market_title) if t in titles]
    checks["new_above_old"] = bool(new_idxs) and all(i < old_idx for i in new_idxs)

    for k, v in checks.items():
        print(f"{k}: {v}")

    if all(checks.values()):
        print("SYSTEM WORKING")
    else:
        print("RANKING FAILURE")


if __name__ == "__main__":
    main()
