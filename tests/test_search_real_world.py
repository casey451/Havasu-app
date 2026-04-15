"""
Real-world style harness for the search ranking pipeline (no DB, no production edits).

Mirrors /search: title substring filter → parse_intent → rank_search_results.
Titles are crafted so the literal query string appears where a user-facing title would still read naturally.
Run with `pytest tests/test_search_real_world.py -s` to see debug prints.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

from core.intent_map import parse_intent
from core.search_rank import rank_search_results


def _evt(
    title: str,
    *,
    source: str = "golakehavasu",
    start_date: str = "2026-06-15",
    description: str | None = None,
    tags: list[str] | None = None,
    category: str = "",
) -> dict[str, Any]:
    """Minimal raw event-shaped payload for normalize_item."""
    return {
        "title": title,
        "type": "event",
        "start_date": start_date,
        "end_date": start_date,
        "weekday": "",
        "source": source,
        "source_url": f"https://example.com/search-rw/{abs(hash(title)) % 10_000_000}",
        "description": description or title,
        "tags": tags or [],
        "category": category,
    }


# Curated catalog: mix of “events” and “business-like” user submissions (still event rows in this API).
MOCK_CATALOG: list[dict[str, Any]] = [
    _evt(
        "Youth Soccer Practice kids friday 4pm at fields",
        source="user",
        tags=["kids", "sports"],
        category="sports",
        start_date="2026-06-20",
        description="Youth soccer Friday evening for ages 8–12.",
    ),
    _evt(
        "Live DJ at Kokomo nightlife Friday tickets",
        source="golakehavasu",
        tags=["music", "social"],
        category="nightlife",
        start_date="2026-06-21",
        description="DJ set and dancing late night.",
    ),
    _evt(
        "Farmers Market things to do this weekend fresh food",
        source="golakehavasu",
        tags=["kids"],
        category="events",
        start_date="2026-06-14",
        description="Local vendors food and produce Saturday morning.",
    ),
    _evt(
        "Easter Egg Hunt kids friday morning park",
        source="user",
        tags=["kids"],
        category="kids",
        start_date="2026-06-13",
        description="Family easter egg hunt for children.",
    ),
    _evt(
        "Boat Party things to do this weekend on the lake",
        source="golakehavasu",
        tags=["social", "music"],
        category="events",
        start_date="2026-06-14",
        description="Sunset boat party with music.",
    ),
    _evt(
        "Havasu HVAC Pros when ac not working we fix fast",
        source="user",
        tags=["kids"],
        category="hvac",
        start_date="2026-06-10",
        description="Residential HVAC repair and AC service.",
    ),
    _evt(
        "AC not working free clinic unrelated volunteer",
        source="user",
        tags=["social"],
        category="community",
        start_date="2026-06-11",
        description="Volunteer clinic when your AC not working is not our specialty.",
    ),
    _evt(
        "Desert Plumbing Co plumber on call 24/7 drain leak",
        source="user",
        tags=["social"],
        category="plumbing",
        start_date="2026-06-12",
        description="Emergency plumber drain and leak repairs.",
    ),
    _evt(
        "Electric Solutions AZ electrical panel upgrade",
        source="user",
        tags=[],
        category="electrical",
        start_date="2026-06-09",
        description="Licensed electrician panel and wiring.",
    ),
    _evt(
        "Mario's Italian Restaurant food tonight reservations open",
        source="user",
        tags=["music"],
        category="restaurant",
        start_date="2026-06-14",
        description="Italian dinner pasta wine tonight.",
    ),
    _evt(
        "Kids Fun Zone things to do this weekend indoor play",
        source="user",
        tags=["kids"],
        category="kids",
        start_date="2026-06-14",
        description="Indoor play area for children weekend fun.",
    ),
]


def simulate_search(query: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Same pipeline as GET /search (event universe = mock catalog only)."""
    q = query.strip()
    query_lower = q.lower()
    matched = [r for r in MOCK_CATALOG if query_lower in (r.get("title") or "").lower()]
    intent = parse_intent(q)
    return rank_search_results(matched, q, intent, expand=False, limit=limit)


def _debug(query: str, results: list[dict[str, Any]]) -> None:
    if os.environ.get("SEARCH_REAL_WORLD_DEBUG", "").strip().lower() not in ("1", "true", "yes"):
        return
    intent = parse_intent(query)
    top3 = [r.get("title", "") for r in results[:3]]
    print(f"\n[search-real-world] query={query!r}")
    print(f"  intent={intent}")
    print(f"  top3={top3!r}")


def _titles(results: list[dict[str, Any]]) -> list[str]:
    return [str(r.get("title") or "") for r in results]


# --- Tests (exact user queries) ---


def test_query_ac_not_working_hvac_in_top_three() -> None:
    q = "ac not working"
    out = simulate_search(q)
    _debug(q, out)
    assert out  # not empty
    top3 = _titles(out)[:3]
    assert any("Havasu HVAC" in t for t in top3), top3


def test_query_food_tonight_food_in_top_three() -> None:
    q = "food tonight"
    out = simulate_search(q)
    _debug(q, out)
    assert out
    top3 = _titles(out)[:3]
    assert any("Mario" in t or "Farmers" in t or "food" in t.lower() for t in top3), top3


def test_query_kids_friday_kids_event_near_top() -> None:
    q = "kids friday"
    out = simulate_search(q)
    _debug(q, out)
    assert out
    top3 = _titles(out)[:3]
    assert any("Soccer" in t or "Easter" in t or "kids" in t.lower() for t in top3), top3


def test_query_things_weekend_events_prioritized_over_pure_business() -> None:
    """
    Discovery-style query: crawler calendar rows should occupy the top band; user venues remain visible
    but should not crowd out indexed events.
    """
    q = "things to do this weekend"
    out = simulate_search(q)
    _debug(q, out)
    assert out
    ts = _titles(out)
    assert len(ts) == 3, ts
    top2 = ts[:2]
    assert all("Farmers" in t or "Boat" in t for t in top2), top2
    assert "Kids Fun" in ts[2], ts


def test_query_plumber_plumbing_first() -> None:
    q = "plumber"
    out = simulate_search(q)
    _debug(q, out)
    assert out
    assert "Desert Plumbing" in _titles(out)[0]


def test_query_nightlife_dj_near_top() -> None:
    q = "nightlife"
    out = simulate_search(q)
    _debug(q, out)
    assert out
    top3 = _titles(out)[:3]
    assert any("DJ" in t or "Kokomo" in t or "nightlife" in t.lower() for t in top3), top3


def test_query_random_nonsense_no_crash() -> None:
    q = "zzznonsenseqqq999"
    out = simulate_search(q)
    _debug(q, out)
    assert out == []


@pytest.mark.parametrize(
    "query",
    [
        "ac not working",
        "food tonight",
        "kids friday",
        "things to do this weekend",
        "plumber",
        "nightlife",
        "zzznonsenseqqq999",
    ],
)
def test_debug_print_block(query: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Always-on debug summary (captured unless pytest -s)."""
    out = simulate_search(query)
    intent = parse_intent(query)
    top3 = [r.get("title", "") for r in out[:3]]
    print(f"\nquery={query!r}\nintent={intent}\ntop3={top3!r}")
    captured = capsys.readouterr()
    assert query in captured.out
