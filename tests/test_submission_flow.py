from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def _payload(title: str) -> dict:
    return {
        "title": title,
        "description": "submitted from tests",
        "tags": ["plumber", "repair"],
        "intent_tags": ["emergency", "after hours"],
        "category": "service",
        "event_time": "2026-06-15T18:00:00",
        "location": "Lake Havasu",
    }


def test_submit_creates_pending_row(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    r = c.post("/submit", json=_payload("Submit Pending A"))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    pid = body["id"]

    pending = c.get("/admin/pending", headers=admin_headers)
    assert pending.status_code == 200
    rows = pending.json()
    assert any(x["id"] == pid and x["status"] == "pending" for x in rows)


def test_duplicate_submission_not_inserted(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    first = c.post("/submit", json=_payload("Duplicate Title"))
    assert first.status_code == 200
    first_id = first.json()["id"]
    second = c.post("/submit", json=_payload("  duplicate title  "))
    assert second.status_code == 200
    body = second.json()
    assert body["success"] is True
    assert body["duplicate"] is True
    assert body["id"] == first_id
    pending = c.get("/admin/pending", headers=admin_headers).json()
    hits = [x for x in pending if x.get("title", "").lower().strip() == "duplicate title"]
    assert len(hits) == 1


def test_pending_not_returned_in_search(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    title = "Ultra Unique Pending Service"
    c.post("/submit", json=_payload(title))
    r = c.get("/search", params={"q": "Ultra Unique Pending Service"})
    assert r.status_code == 200
    titles = [x.get("title", "") for x in r.json()["results"]]
    assert title not in titles


def test_approved_shows_in_search(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    title = "Unique Approved Service Listing"
    created = c.post("/submit", json=_payload(title))
    sid = created.json()["id"]
    ap = c.post("/admin/approve", params={"id": sid}, headers=admin_headers)
    assert ap.status_code == 200

    r = c.get("/search", params={"q": "Unique Approved Service Listing"})
    assert r.status_code == 200
    titles = [x.get("title", "") for x in r.json()["results"]]
    assert title in titles


def test_non_havasu_allowed(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    body = _payload("Out of Area")
    body["location"] = "Phoenix"
    r = c.post("/submit", json=body)
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_missing_title_rejected(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    body = _payload("x")
    body["title"] = "   "
    r = c.post("/submit", json=body)
    assert r.status_code == 400
    assert r.json() == {"error": "invalid_submission"}


def test_missing_event_time_allowed(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    body = _payload("Valid Title")
    body["event_time"] = ""
    r = c.post("/submit", json=body)
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_missing_category_rejected(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    body = _payload("Valid Title")
    body["category"] = "   "
    r = c.post("/submit", json=body)
    assert r.status_code == 400
    assert "category is required" in r.text


def test_bad_title_rejected(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    for bad in ("test", "asdf", "12345", "!!!", "ab"):
        body = _payload(bad)
        r = c.post("/submit", json=body)
        assert r.status_code == 400
        assert r.json() == {"error": "invalid_submission"}


def test_feature_requires_approved_submission(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    created = c.post("/submit", json=_payload("Pending Not Featureable"))
    sid = created.json()["id"]
    r = c.post("/admin/feature", params={"id": sid, "days": 7}, headers=admin_headers)
    assert r.status_code == 404


def test_feature_then_unfeature_updates_search_item(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    title = "Featured Weekend Service"
    sid = c.post("/submit", json=_payload(title)).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    assert c.post("/admin/feature", params={"id": sid, "days": 7}, headers=admin_headers).status_code == 200

    body = c.get("/search", params={"q": title}).json()
    hit = next((x for x in body["results"] if x.get("title") == title), None)
    assert hit is not None
    assert hit.get("is_featured") is True

    assert c.post("/admin/unfeature", params={"id": sid}, headers=admin_headers).status_code == 200
    body2 = c.get("/search", params={"q": title}).json()
    hit2 = next((x for x in body2["results"] if x.get("title") == title), None)
    assert hit2 is not None
    assert hit2.get("is_featured") in (False, None)


def test_track_view_and_click_increment(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    title = "Trackable Listing"
    sid = c.post("/submit", json=_payload(title)).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200

    assert c.post("/track/view", json={"id": sid}).status_code == 200
    assert c.post("/track/click", json={"id": sid}).status_code == 200

    approved = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    row = next((x for x in approved if x["id"] == sid), None)
    assert row is not None
    assert int(row["view_count"]) == 1
    assert int(row["click_count"]) == 1


def test_track_view_dedup_same_ip_within_window(
    fresh_db,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("View Dedup Listing")).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    import api.main as m

    m._track_seen.clear()
    t = {"v": 1000.0}
    monkeypatch.setattr(m, "_tracking_now", lambda: t["v"])

    headers = {"x-forwarded-for": "10.1.1.1"}
    assert c.post("/track/view", json={"id": sid}, headers=headers).status_code == 200
    assert c.post("/track/view", json={"id": sid}, headers=headers).status_code == 200

    approved = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    row = next((x for x in approved if x["id"] == sid), None)
    assert row is not None
    assert int(row["view_count"]) == 1


def test_track_view_increments_after_window(
    fresh_db,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("View Window Listing")).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    import api.main as m

    m._track_seen.clear()
    t = {"v": 2000.0}
    monkeypatch.setattr(m, "_tracking_now", lambda: t["v"])

    headers = {"x-forwarded-for": "10.1.1.2"}
    assert c.post("/track/view", json={"id": sid}, headers=headers).status_code == 200
    t["v"] += 601.0
    assert c.post("/track/view", json={"id": sid}, headers=headers).status_code == 200

    approved = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    row = next((x for x in approved if x["id"] == sid), None)
    assert row is not None
    assert int(row["view_count"]) == 2


def test_track_view_different_ip_increments(
    fresh_db,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("View IP Listing")).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    import api.main as m

    m._track_seen.clear()
    monkeypatch.setattr(m, "_tracking_now", lambda: 3000.0)

    assert c.post("/track/view", json={"id": sid}, headers={"x-forwarded-for": "10.1.1.3"}).status_code == 200
    assert c.post("/track/view", json={"id": sid}, headers={"x-forwarded-for": "10.1.1.4"}).status_code == 200

    approved = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    row = next((x for x in approved if x["id"] == sid), None)
    assert row is not None
    assert int(row["view_count"]) == 2


def test_track_click_dedup_same_ip_within_window(
    fresh_db,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("Click Dedup Listing")).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    import api.main as m

    m._track_seen.clear()
    monkeypatch.setattr(m, "_tracking_now", lambda: 4000.0)
    headers = {"x-forwarded-for": "10.1.1.5"}
    assert c.post("/track/click", json={"id": sid}, headers=headers).status_code == 200
    assert c.post("/track/click", json={"id": sid}, headers=headers).status_code == 200

    approved = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    row = next((x for x in approved if x["id"] == sid), None)
    assert row is not None
    assert int(row["click_count"]) == 1


def test_track_invalid_id_no_crash(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    assert c.post("/track/view", json={"id": "does-not-exist"}).status_code == 200
    assert c.post("/track/click", json={"id": "does-not-exist"}).status_code == 200


def test_notifications_feed_empty_when_no_approved(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    r = c.get("/notifications/feed")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["items"] == []


def test_notifications_feed_includes_new_approved_item(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("Notify Me Event")).json()["id"]
    # pending should not appear
    pending_body = c.get("/notifications/feed").json()
    assert all(x.get("id") != sid for x in pending_body["items"])
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    approved_body = c.get("/notifications/feed").json()
    hit = next((x for x in approved_body["items"] if x.get("id") == sid), None)
    assert hit is not None
    assert hit["title"] == "Notify Me Event"


def test_intent_tags_not_exposed_publicly(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("Hidden Intent Service")).json()["id"]
    assert c.post("/admin/approve", params={"id": sid}, headers=admin_headers).status_code == 200
    search_body = c.get("/search", params={"q": "Hidden Intent Service"}).json()
    assert all("intent_tags" not in row for row in search_body.get("results", []))
    admin_rows = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    admin_hit = next((x for x in admin_rows if x.get("id") == sid), None)
    assert admin_hit is not None
    assert "intent_tags" not in admin_hit


def test_admin_path_approve_and_reject_flow(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    sid = c.post("/submit", json=_payload("Path Approval Listing")).json()["id"]
    assert c.post(f"/admin/approve/{sid}", headers=admin_headers).status_code == 200
    approved_rows = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    assert any(x.get("id") == sid for x in approved_rows)
    assert c.post(f"/admin/reject/{sid}", headers=admin_headers).status_code == 200
    approved_rows_2 = c.get("/admin/submissions", params={"status": "approved"}, headers=admin_headers).json()
    rejected_rows = c.get("/admin/submissions", params={"status": "rejected"}, headers=admin_headers).json()
    assert all(x.get("id") != sid for x in approved_rows_2)
    assert any(x.get("id") == sid for x in rejected_rows)


def test_admin_endpoints_require_token(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    r = c.get("/admin/pending")
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_admin_endpoints_reject_wrong_token(fresh_db) -> None:
    _ = fresh_db
    c = TestClient(app)
    r = c.get("/admin/pending", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_admin_endpoints_accept_correct_token(fresh_db, admin_headers: dict[str, str]) -> None:
    _ = fresh_db
    c = TestClient(app)
    r = c.get("/admin/pending", headers=admin_headers)
    assert r.status_code == 200
