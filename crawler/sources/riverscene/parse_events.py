from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from crawler.sources.golakehavasu.parse_events import extract_date_range, extract_time_range
from crawler.sources.riverscene.date_signals import title_implies_seasonal_mismatch

_MAX_DESCRIPTION_LEN = 280


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _clean_description(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if len(text) > _MAX_DESCRIPTION_LEN:
        text = text[: _MAX_DESCRIPTION_LEN].rstrip() + "…"
    return text


def _strip_rendered_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _first_sentence(text: str | None) -> str | None:
    if not text:
        return None
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return _clean_text(text)[:200] or None
    return sentences[0]


def _main_content_text(soup: BeautifulSoup) -> str:
    """Prefer event/article body over sidebars (publish dates, widgets)."""
    for sel in (
        "article .entry-content",
        ".tribe-events-single-event-description",
        "article .elementor-widget-theme-post-content",
        "article",
        "main",
        "#content",
    ):
        node = soup.select_one(sel)
        if node:
            t = _clean_text(node.get_text(" ", strip=True))
            if len(t) >= 40:
                return t
    return ""


def _strip_boilerplate(soup: BeautifulSoup) -> BeautifulSoup:
    """Drop common WP/Tribe blocks that carry publish/update dates."""
    for tag in soup(["script", "style"]):
        tag.decompose()
    for sel in ("aside", "footer", "nav"):
        for el in soup.find_all(sel):
            el.decompose()
    for el in soup.find_all("time"):
        cls = " ".join(el.get("class") or []).lower()
        if any(
            x in cls
            for x in (
                "entry-date",
                "published",
                "updated",
                "post-date",
                "dt-published",
            )
        ):
            el.decompose()
    for el in soup.find_all(class_=re.compile(r"posted-on|post-meta|byline|entry-meta", re.I)):
        el.decompose()
    return soup


def parse_wordpress_post(post: dict[str, Any]) -> dict[str, Any]:
    """
    Map a WordPress REST post object into the shared parser output shape.
    All fields come from the API payload (HTML in rendered fields is stripped to text).
    """
    title_html = (post.get("title") or {}).get("rendered") or ""
    content_html = (post.get("content") or {}).get("rendered") or ""

    title = _clean_text(_strip_rendered_html(title_html))
    description = _clean_description(_strip_rendered_html(content_html))
    link = (post.get("link") or "").strip()

    # Dates: prefer title + visible description (REST body), not full HTML with meta noise.
    primary_blob = "\n".join(filter(None, [title, description]))
    start_d, end_d = extract_date_range(primary_blob)
    date_src = "event_body_text"
    if start_d is None and end_d is None:
        start_d, end_d = extract_date_range(content_html)
        date_src = "content_html_fallback"

    start_t, end_t = extract_time_range(primary_blob)
    if start_t is None and end_t is None:
        start_t, end_t = extract_time_range("\n".join(filter(None, [title, description, content_html])))

    date_text: str | None = None
    if start_d and end_d:
        if start_d == end_d:
            date_text = start_d.isoformat()
        else:
            date_text = f"{start_d.isoformat()} – {end_d.isoformat()}"
    elif start_d:
        date_text = start_d.isoformat()

    short_description = _first_sentence(description)

    # HTML/meta fallback can still pick publish noise — mark low for homepage gating.
    conf = "low" if date_src == "content_html_fallback" else "high"

    return {
        "title": title or None,
        "start_date": start_d,
        "end_date": end_d,
        "date_raw": date_text,
        "date_text": date_text,
        "start_time": start_t,
        "end_time": end_t,
        "venue_name": None,
        "address": None,
        "description": description,
        "short_description": short_description,
        "source_url": link or None,
        "riverscene_date_source": date_src,
        "riverscene_date_confidence": conf,
    }


_NOISE_SUBSTRINGS = (
    "cookie",
    "riverscene magazine is your fresh resource",
    "copyright",
    "strictly necessary cookie",
    "redemption theme",
    "useful links",
    "advertise with us",
    "recent havasu news",
)


def parse_event_detail_html(html: str, source_url: str = "") -> dict[str, Any]:
    """
    Parse a RiverScene event detail page (Elementor / WP front-end HTML).
    Dates often live only in body copy — extract from full text before description length cap.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = _clean_text(og["content"])
    if not title and soup.title and soup.title.string:
        raw_title = soup.title.string
        if "|" in raw_title:
            title = _clean_text(raw_title.split("|")[-1])
        else:
            title = _clean_text(raw_title)
    if not title:
        h2 = soup.find("h2")
        if h2:
            title = _clean_text(h2.get_text())

    paragraphs: list[str] = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if len(t) < 18:
            continue
        tl = t.lower()
        if any(n in tl for n in _NOISE_SUBSTRINGS):
            continue
        if t.strip().lower() in ("no address available",):
            continue
        paragraphs.append(t)

    # Uncapped body text for date extraction (display description still capped below).
    desc_full = _clean_text("\n".join(paragraphs))
    description = _clean_description(desc_full)

    # Dates: NEVER use full document text — it includes publish/meta ISO dates and widget noise.
    primary_blob = _clean_text(f"{title}\n{desc_full}".strip())
    start_d, end_d = extract_date_range(primary_blob)
    date_src = "event_body_text"
    conf = "high"
    main_txt = ""

    if start_d is None and end_d is None:
        soup_main = _strip_boilerplate(BeautifulSoup(html, "html.parser"))
        main_txt = _main_content_text(soup_main)
        if main_txt:
            start_d, end_d = extract_date_range(main_txt)
            if start_d is not None or end_d is not None:
                date_src = "main_column_text"
                conf = "medium"

    # No whole-document fallback — missing date beats wrong date on the homepage.
    if start_d is None and end_d is None:
        date_src = "no_date_extracted"
        conf = "none"

    if start_d is not None and title_implies_seasonal_mismatch(title, start_d):
        start_d, end_d = None, None
        date_src = "rejected_title_season_mismatch"
        conf = "none"  # no date retained; homepage filter also excludes riverscene without medium/high

    start_t, end_t = extract_time_range(primary_blob)
    if start_t is None and end_t is None and main_txt:
        start_t, end_t = extract_time_range(main_txt)

    date_text: str | None = None
    if start_d and end_d:
        if start_d == end_d:
            date_text = start_d.isoformat()
        else:
            date_text = f"{start_d.isoformat()} – {end_d.isoformat()}"
    elif start_d:
        date_text = start_d.isoformat()

    short_description = _first_sentence(description)

    link = str(source_url).strip() if source_url else None

    return {
        "title": title or None,
        "start_date": start_d,
        "end_date": end_d,
        "date_raw": date_text,
        "date_text": date_text,
        "start_time": start_t,
        "end_time": end_t,
        "venue_name": None,
        "address": None,
        "description": description,
        "short_description": short_description,
        "source_url": link,
        "riverscene_date_source": date_src,
        "riverscene_date_confidence": conf,
    }


def parse_event_page(html: str, source_url: str = "") -> dict[str, Any]:
    """
    Stored raw_pages rows may be WP REST JSON (legacy) or HTML from an event URL.
    """
    stripped = html.lstrip()
    if stripped.startswith("{"):
        try:
            post = json.loads(html)
        except json.JSONDecodeError:
            post = None
        else:
            if isinstance(post, dict) and "title" in post and "link" in post:
                parsed = parse_wordpress_post(post)
                if source_url and not parsed.get("source_url"):
                    parsed["source_url"] = source_url.strip() or None
                return parsed

    return parse_event_detail_html(html, source_url=source_url)
