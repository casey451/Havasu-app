"""Homepage calendar trust: RiverScene dates + gating (no network)."""
from __future__ import annotations

from crawler.sources.riverscene.parse_events import parse_event_detail_html
from core.calendar_filters import include_in_homepage_calendar_lists


def test_reject_publish_date_fallback() -> None:
    """Only a visible publish/meta line has a date; event body has no calendar day → no start_date."""
    html = """
    <html><head>
    <meta property="og:title" content="Some Community Event" />
    </head><body>
    <div class="posted-on"><time datetime="2026-04-14">April 14, 2026</time></div>
    <article><div class="entry-content">
    <p>Bring the family for fun and games. Hours 10:00 a.m. to 2:00 p.m. No date mentioned here.</p>
    </div></article>
    </body></html>
    """
    out = parse_event_detail_html(html, source_url="https://riverscenemagazine.com/events/x/")
    assert out.get("start_date") is None
    assert out.get("riverscene_date_source") == "no_date_extracted"


def test_accept_valid_event_date() -> None:
    """Clear event copy with a real calendar phrase → parsed ISO date."""
    html = """
    <html><body><article><div class="entry-content">
    <p>Join us on December 31, 2026 for the countdown. Doors open at 9:00 p.m.</p>
    </div></article></body></html>
    """
    out = parse_event_detail_html(html, source_url="https://riverscenemagazine.com/events/y/")
    assert str(out.get("start_date")) == "2026-12-31"
    assert out.get("riverscene_date_confidence") == "high"


def test_reject_season_mismatch() -> None:
    """NYE-style title + April body date → we drop the date (prefer missing over wrong)."""
    html = """
    <html><head>
    <meta property="og:title" content="New Year's Eve Balloon Drop" />
    </head><body><article><div class="entry-content">
    <p>Wrong line: April 14, 2026 was pasted from somewhere.</p>
    </div></article></body></html>
    """
    out = parse_event_detail_html(html, source_url="https://riverscenemagazine.com/events/z/")
    assert out.get("start_date") is None
    assert out.get("riverscene_date_source") == "rejected_title_season_mismatch"


def test_no_date_does_not_guess() -> None:
    """Times only, no calendar day → no invented start_date."""
    html = """
    <html><body><article><div class="entry-content">
    <p>Open swim blocks 10:00 a.m. to 2:00 p.m. Call for details.</p>
    </div></article></body></html>
    """
    out = parse_event_detail_html(html, source_url="https://riverscenemagazine.com/events/t/")
    assert out.get("start_date") is None


def test_today_filter_excludes_null_dates() -> None:
    """Homepage lists require start_date; RiverScene also requires medium/high confidence."""
    assert not include_in_homepage_calendar_lists(
        {"source": "riverscene", "type": "event", "start_date": None},
    )
    assert not include_in_homepage_calendar_lists(
        {
            "source": "riverscene",
            "type": "event",
            "start_date": "2026-06-01",
            "riverscene_date_confidence": "low",
        },
    )
    assert not include_in_homepage_calendar_lists(
        {
            "source": "riverscene",
            "type": "event",
            "start_date": "2026-06-01",
        },
    )
    assert include_in_homepage_calendar_lists(
        {
            "source": "riverscene",
            "type": "event",
            "start_date": "2026-06-01",
            "riverscene_date_confidence": "high",
        },
    )
    assert include_in_homepage_calendar_lists(
        {
            "source": "golakehavasu",
            "type": "event",
            "start_date": "2026-06-01",
        },
    )
    assert include_in_homepage_calendar_lists(
        {
            "source": "user",
            "type": "event",
            "start_date": "2026-06-01",
        },
    )


def test_today_filter_excludes_confidence_none_string() -> None:
    assert not include_in_homepage_calendar_lists(
        {
            "source": "riverscene",
            "type": "event",
            "start_date": "2026-06-01",
            "riverscene_date_confidence": "none",
        },
    )
