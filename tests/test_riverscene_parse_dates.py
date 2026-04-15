from __future__ import annotations

from crawler.sources.riverscene.parse_events import parse_event_detail_html


def test_detail_parse_ignores_publish_iso_outside_entry_content() -> None:
    """Publish ISO in header must not become event start_date when body has no that date."""
    html = """
    <html><head>
    <meta property="og:title" content="Altitude's Noon Year's Eve Balloon Drop" />
    <title>Altitude's Noon Year's Eve Balloon Drop | RiverScene</title>
    </head>
    <body>
    <div class="posted-on"><time datetime="2026-04-14">April 14, 2026</time></div>
    <article>
      <div class="entry-content">
        <p>Jump into the annual Noon Year's Eve balloon drop with games. 10:00 a.m. to 2:00 p.m.</p>
      </div>
    </article>
    </body></html>
    """
    out = parse_event_detail_html(html, source_url="https://riverscenemagazine.com/events/x/")
    assert out.get("start_date") is None
    assert out.get("end_date") is None
    assert out.get("riverscene_date_confidence") == "none"


def test_detail_parse_prefers_body_date_over_noise() -> None:
    html = """
    <html><body>
    <article><div class="entry-content">
    <p>Join us on December 31, 2026 for a balloon drop. Doors at 10:00 a.m.</p>
    </div></article>
    </body></html>
    """
    out = parse_event_detail_html(html, source_url="https://example.com/e/")
    assert out.get("start_date") is not None
    assert str(out["start_date"]) == "2026-12-31"
