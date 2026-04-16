from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def test_ai_intake_plumber_flow_creates_pending_submission(
    fresh_db,
    admin_headers: dict[str, str],
) -> None:
    _ = fresh_db
    c = TestClient(app)

    start = c.post("/ai/intake/start", json={"message": "I run a plumbing company"})
    assert start.status_code == 200
    started = start.json()
    assert started["category"] == "plumber"
    assert isinstance(started["questions"], list)
    assert len(started["questions"]) >= 4
    sid = started["session_id"]

    answers = [
        "Rapid Flow Plumbing",
        "Yes, emergency and after hours calls",
        "Drain cleaning and water heater replacement",
        "Residential and commercial",
        "Lake Havasu City",
    ]
    final = None
    for ans in answers:
        r = c.post("/ai/intake/answer", json={"session_id": sid, "answer": ans})
        assert r.status_code == 200
        final = r.json()
    assert final is not None
    assert final["done"] is True
    preview = final["preview"]
    assert preview["title"] == "Rapid Flow Plumbing"
    assert preview["category"] == "plumber"
    assert "emergency" in preview["intent_tags"]
    assert "water_heater" in preview["intent_tags"]
    assert preview["location"] == "Lake Havasu City"

    submit = c.post("/ai/intake/submit", json={"session_id": sid})
    assert submit.status_code == 200
    payload = submit.json()
    assert payload["success"] is True
    created_id = payload["id"]

    pending = c.get("/admin/submissions", params={"status": "pending"}, headers=admin_headers)
    assert pending.status_code == 200
    rows = pending.json()
    hit = next((x for x in rows if x.get("id") == created_id), None)
    assert hit is not None
    assert hit.get("status") == "pending"


def test_ai_intake_submit_requires_location(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    start = c.post("/ai/intake/start", json={"message": "we are an electrician service"})
    sid = start.json()["session_id"]

    answers = [
        "Wire Pros",
        "Panel and outlet work",
        "No emergency",
        "Residential",
        "   ",
    ]
    for ans in answers:
        c.post("/ai/intake/answer", json={"session_id": sid, "answer": ans})

    submit = c.post("/ai/intake/submit", json={"session_id": sid})
    assert submit.status_code == 400
    assert "location is required" in submit.text
