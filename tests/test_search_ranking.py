"""PHASE 2 — search ranking boosts (unit tests)."""
from __future__ import annotations

from datetime import date, timedelta

from core.search_rank import rank_search_results, score_item
from core.serialize import finalize_api_list


def _norm_item(**kwargs: object) -> dict:
    """Minimal normalized-shaped dict for score_item."""
    base = {
        # Avoid accidental INTENT keyword substrings (e.g. in "Event").
        "title": "Plain title xyz123",
        "tags": [],
        "category": "",
        "source": "golakehavasu",
        "trust_score": 0.5,
        "start_date": "2026-12-01",
    }
    base.update(kwargs)
    return base


def test_tag_match_boost() -> None:
    intent = {"tags": ["kids"], "category": "kids", "confidence": 0.5}
    low = _norm_item(tags=["music"])
    high = _norm_item(tags=["kids"])
    assert score_item(high, intent) > score_item(low, intent)


def test_category_match_boost() -> None:
    intent = {"tags": ["food"], "category": "food", "confidence": 0.5}
    miss = _norm_item(category="hvac repair")
    hit = _norm_item(category="breakfast food")
    assert score_item(hit, intent) > score_item(miss, intent)


def test_low_confidence_no_boost_order_matches_finalize() -> None:
    raw = [
        {
            "title": "Zebra",
            "type": "event",
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
            "source": "golakehavasu",
            "source_url": "https://example.com/z",
            "description": "d",
        },
        {
            "title": "Alpha",
            "type": "event",
            "start_date": "2026-08-02",
            "end_date": "2026-08-02",
            "source": "golakehavasu",
            "source_url": "https://example.com/a",
            "description": "d",
        },
    ]
    intent = {"tags": [], "category": None, "confidence": 0.08}
    ranked = rank_search_results(raw, "unused", intent, False, 10)
    baseline = finalize_api_list(raw, False)
    assert [x.get("title") for x in ranked] == [x.get("title") for x in baseline]


def test_business_priority() -> None:
    intent = {"tags": ["food"], "category": "food", "confidence": 0.5}
    crawl = _norm_item(source="golakehavasu", category="food", trust_score=1.0)
    user = _norm_item(source="user", category="food", trust_score=1.0)
    assert score_item(user, intent) > score_item(crawl, intent)


def test_recency_boost() -> None:
    today = date.today()
    soon = (today + timedelta(days=4)).isoformat()
    far = (today + timedelta(days=80)).isoformat()
    intent = {"tags": ["events"], "category": "events", "confidence": 0.5}
    a = _norm_item(start_date=far, title="Concert A")
    b = _norm_item(start_date=soon, title="Concert B")
    assert score_item(b, intent) > score_item(a, intent)


def test_event_in_1_day_beats_10_days() -> None:
    today = date.today()
    near = _norm_item(start_date=(today + timedelta(days=1)).isoformat(), title="Near Event")
    mid = _norm_item(start_date=(today + timedelta(days=10)).isoformat(), title="Mid Event")
    intent = {"tags": ["events"], "category": "events", "confidence": 0.6}
    assert score_item(near, intent, query="things to do this weekend") > score_item(
        mid, intent, query="things to do this weekend"
    )


def test_phrase_matching_food_tonight_boosts_restaurant_title() -> None:
    intent = {"tags": ["food"], "category": "food", "confidence": 0.6}
    rest = _norm_item(
        title="Food tonight at Mario's Restaurant",
        tags=["dining"],
        category="food",
    )
    weak = _norm_item(
        title="Community meetup",
        tags=["social"],
        category="community",
    )
    assert score_item(rest, intent, query="food tonight") > score_item(weak, intent, query="food tonight")


def test_fallback_never_above_real_data() -> None:
    intent = {"tags": ["events"], "category": "events", "confidence": 0.7}
    real = _norm_item(
        title="Lake Event this weekend",
        source="golakehavasu",
        category="events",
    )
    fallback = _norm_item(
        title="Popular this weekend",
        source="fallback",
        category="events",
    )
    assert score_item(real, intent, query="things to do this weekend") > score_item(
        fallback, intent, query="things to do this weekend"
    )


def test_past_event_ranks_below_future_event() -> None:
    today = date.today()
    past = _norm_item(start_date=(today - timedelta(days=2)).isoformat(), title="Past Event")
    future = _norm_item(start_date=(today + timedelta(days=2)).isoformat(), title="Future Event")
    intent = {"tags": ["events"], "category": "events", "confidence": 0.5}
    assert score_item(future, intent, query="events") > score_item(past, intent, query="events")


def test_featured_item_gets_controlled_boost() -> None:
    intent = {"tags": ["events"], "category": "events", "confidence": 0.5}
    base = _norm_item(title="Weekend Concert", category="events")
    featured = _norm_item(
        title="Weekend Concert",
        category="events",
        is_featured=True,
        featured_until="2099-01-01T00:00:00+00:00",
    )
    assert score_item(featured, intent, query="events") > score_item(base, intent, query="events")


def test_expired_featured_loses_boost() -> None:
    intent = {"tags": ["events"], "category": "events", "confidence": 0.5}
    expired = _norm_item(
        title="Old Featured",
        category="events",
        is_featured=True,
        featured_until="2000-01-01T00:00:00+00:00",
    )
    normal = _norm_item(title="Old Featured", category="events")
    assert score_item(expired, intent, query="events") <= score_item(normal, intent, query="events")


def test_featured_does_not_override_irrelevant_result() -> None:
    intent = {"tags": ["food"], "category": "food", "confidence": 0.8}
    relevant = _norm_item(title="Food tonight at Bistro", category="food", tags=["food"])
    featured_irrelevant = _norm_item(
        title="Boat Repair Expo",
        category="marine",
        tags=["boats"],
        is_featured=True,
        featured_until="2099-01-01T00:00:00+00:00",
    )
    assert score_item(relevant, intent, query="food tonight") > score_item(
        featured_irrelevant, intent, query="food tonight"
    )


def test_high_views_do_not_overpower_strong_relevance() -> None:
    intent = {"tags": ["food"], "category": "food", "confidence": 0.8}
    relevant = _norm_item(
        title="Food tonight at Bistro",
        category="food",
        tags=["food", "dining"],
        view_count=2,
        click_count=1,
    )
    stale_popular = _norm_item(
        title="Annual boat expo",
        category="marine",
        tags=["boats"],
        view_count=100000,
        click_count=10000,
    )
    assert score_item(relevant, intent, query="food tonight") > score_item(
        stale_popular, intent, query="food tonight"
    )


def test_new_event_beats_old_high_view_event() -> None:
    today = date.today()
    intent = {"tags": ["events"], "category": "events", "confidence": 0.6}
    upcoming = _norm_item(
        title="Weekend concert",
        start_date=(today + timedelta(days=1)).isoformat(),
        view_count=5,
        click_count=2,
        category="events",
    )
    old_heavy = _norm_item(
        title="Old listing",
        start_date=(today - timedelta(days=30)).isoformat(),
        view_count=100000,
        click_count=10000,
        category="events",
    )
    assert score_item(upcoming, intent, query="events") > score_item(old_heavy, intent, query="events")


def test_future_event_ranks_above_past_even_with_popularity() -> None:
    today = date.today()
    intent = {"tags": ["events"], "category": "events", "confidence": 0.5}
    future = _norm_item(
        title="Future Event",
        start_date=(today + timedelta(days=2)).isoformat(),
        view_count=10,
        click_count=1,
    )
    past = _norm_item(
        title="Past Event",
        start_date=(today - timedelta(days=2)).isoformat(),
        view_count=1000,
        click_count=100,
    )
    assert score_item(future, intent, query="events") > score_item(past, intent, query="events")


def test_log_scaling_reduces_large_count_impact() -> None:
    intent = {"tags": [], "category": None, "confidence": 0.3}
    base = _norm_item(title="Same item")
    plus_small = _norm_item(title="Same item", view_count=10, click_count=10)
    plus_large = _norm_item(title="Same item", view_count=1000, click_count=1000)
    plus_larger = _norm_item(title="Same item", view_count=1010, click_count=1010)
    small_gain = score_item(plus_small, intent, query="") - score_item(base, intent, query="")
    large_gain = score_item(plus_larger, intent, query="") - score_item(plus_large, intent, query="")
    assert large_gain < small_gain
