from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlparse

from core.http import build_client

logger = logging.getLogger(__name__)

SITE_HOST = "riverscenemagazine.com"
BASE_URL = f"https://{SITE_HOST}"
CALENDAR_PAGE_URL = f"{BASE_URL}/calendar-event/"

# Candidate REST bases for a public event list (site has no /wp/v2/events — verified at runtime).
_EVENTS_REST_CANDIDATES: tuple[str, ...] = (
    f"{BASE_URL}/wp-json/tribe/events/v1/events",
    f"{BASE_URL}/wp-json/wp/v2/events",
)

# Embedded calendar JS includes many `/events/.../` strings; anchor tags alone are insufficient.
_EVENT_PATH_RE = re.compile(
    rf"(?:https://{re.escape(SITE_HOST)})?/events/([^/\"'\s#]+)/",
    re.IGNORECASE,
)

_MAX_DISCOVERED_URLS = 500

_EXCLUDED_PATH_SUBSTRINGS: tuple[str, ...] = (
    "/category/",
    "/tag/",
    "/author/",
    "/page/",
    "/wp-json/",
    "/feed/",
)


def _normalize_event_url(href: str) -> str | None:
    href = href.strip().split("#")[0].strip()
    if not href:
        return None
    full = urljoin(BASE_URL + "/", href)
    parsed = urlparse(full)
    if parsed.netloc.lower() != SITE_HOST:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0].lower() != "events":
        return None
    slug = parts[1]
    if not slug or slug.lower() in ("events", "event"):
        return None
    # Single canonical form: trailing slash, no query
    slug_canon = slug
    return f"{BASE_URL}/events/{slug_canon}/"


def is_valid_riverscene_event_url(url: str) -> bool:
    """
    Only calendar detail pages: https://riverscenemagazine.com/events/{slug} (optional trailing /).
    Rejects news, blog, category pages, and any non-/events/ URL.
    """
    u = url.strip()
    if not u:
        return False
    parsed = urlparse(u)
    if parsed.scheme.lower() != "https":
        return False
    if parsed.netloc.lower() != SITE_HOST:
        return False
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) != 2:
        return False
    if path_parts[0].lower() != "events":
        return False
    slug = path_parts[1]
    if not slug or slug.lower() in ("events", "event"):
        return False
    low = u.lower()
    if any(bad in low for bad in _EXCLUDED_PATH_SUBSTRINGS):
        return False
    return True


def filter_dedupe_event_urls(urls: Iterable[str]) -> list[str]:
    """Normalize, dedupe (set), keep only valid event URLs, sort for stable runs."""
    out: set[str] = set()
    for raw in urls:
        n = _normalize_event_url(raw)
        if not n:
            continue
        if is_valid_riverscene_event_url(n):
            out.add(n)
    return sorted(out)


def extract_raw_and_candidates_from_markup(html: str) -> tuple[int, set[str]]:
    """
    Regex scan: (total regex hits, unique normalized URLs before validity filter).
    """
    raw_hits = 0
    candidates: set[str] = set()
    for m in _EVENT_PATH_RE.finditer(html):
        raw_hits += 1
        u = _normalize_event_url(m.group(0))
        if u:
            candidates.add(u)
    return raw_hits, candidates


def extract_event_urls_from_calendar_markup(html: str) -> tuple[int, list[str]]:
    """Backward-compatible: returns (regex_hit_count, filtered sorted URLs)."""
    raw_hits, candidates = extract_raw_and_candidates_from_markup(html)
    filtered = sorted(u for u in candidates if is_valid_riverscene_event_url(u))
    return raw_hits, filtered


def _try_public_events_api(client: Any) -> list[dict[str, Any]] | None:
    """
    If the site exposes a JSON event list, use it. RiverScene currently has no such route.
    Returns None when unavailable; [] only when the endpoint responds with an empty list.
    """
    for url in _EVENTS_REST_CANDIDATES:
        try:
            response = client.get(url, params={"per_page": 100})
        except Exception:
            continue
        if response.status_code != 200:
            continue
        try:
            data = response.json()
        except Exception:
            continue
        if isinstance(data, list):
            logger.info("RiverScene: using events REST list from %s", url)
            return data
    return None


def _urls_from_api_events(records: list[dict[str, Any]]) -> tuple[int, list[str]]:
    raw = len(records)
    candidates_set: set[str] = set()
    for row in records:
        link = (row.get("url") or row.get("link") or "").strip()
        if not link:
            continue
        u = _normalize_event_url(link)
        if u:
            candidates_set.add(u)
    filtered = sorted(u for u in candidates_set if is_valid_riverscene_event_url(u))
    return raw, filtered


def _calendar_html_via_http() -> str:
    with build_client(timeout_seconds=60.0) as client:
        response = client.get(CALENDAR_PAGE_URL)
        response.raise_for_status()
        return response.text


def _calendar_html_via_playwright() -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright is not installed; skipping headless calendar load.")
        return None

    logger.info("RiverScene: loading calendar with Playwright (fallback).")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(CALENDAR_PAGE_URL, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(4_000)
            return page.content()
        finally:
            browser.close()


def discover_calendar_event_urls() -> tuple[list[str], dict[str, Any]]:
    """
    Primary source: calendar page markup (event URLs are embedded in calendar JS).

    1. Probe common WP/event REST list endpoints — use JSON if present.
    2. Otherwise GET the calendar page and extract `/events/{slug}/` URLs from the full HTML.
    3. If that finds nothing, retry with Playwright after JS render.
    """
    stats: dict[str, Any] = {
        "api_listing_found": False,
        "raw_urls_found": 0,
        "unique_candidates_before_rules": 0,
        "filtered_urls_kept": 0,
        "links_from_http_markup": 0,
        "playwright_used": False,
        "links_from_playwright": 0,
    }

    with build_client(timeout_seconds=60.0) as client:
        api_rows = _try_public_events_api(client)
    if api_rows is not None and len(api_rows) > 0:
        stats["api_listing_found"] = True
        raw_n, urls = _urls_from_api_events(api_rows)
        stats["raw_urls_found"] = raw_n
        stats["unique_candidates_before_rules"] = len(
            {
                u
                for u in (
                    _normalize_event_url((x.get("url") or x.get("link") or "").strip())
                    for x in api_rows
                )
                if u
            }
        )
        stats["filtered_urls_kept"] = len(urls)
        if len(urls) > _MAX_DISCOVERED_URLS:
            urls = urls[:_MAX_DISCOVERED_URLS]
            stats["filtered_urls_kept"] = len(urls)
        logger.info(
            "RiverScene calendar discovery (api): raw=%s filtered=%s",
            stats["raw_urls_found"],
            stats["filtered_urls_kept"],
        )
        return urls, stats

    logger.info(
        "RiverScene: no public JSON event list (checked common /wp-json/ routes); "
        "using calendar page markup for /events/… URLs."
    )

    html = _calendar_html_via_http()
    raw_hits, candidates_http = extract_raw_and_candidates_from_markup(html)
    stats["raw_urls_found"] = raw_hits
    stats["links_from_http_markup"] = len(
        [u for u in candidates_http if is_valid_riverscene_event_url(u)]
    )

    urls = sorted(u for u in candidates_http if is_valid_riverscene_event_url(u))
    stats["unique_candidates_before_rules"] = len(candidates_http)

    if not urls:
        stats["playwright_used"] = True
        pw_html = _calendar_html_via_playwright()
        if pw_html:
            raw_pw, candidates_pw = extract_raw_and_candidates_from_markup(pw_html)
            stats["raw_urls_found"] += raw_pw
            stats["links_from_playwright"] = len(
                [u for u in candidates_pw if is_valid_riverscene_event_url(u)]
            )
            candidates_http |= candidates_pw
            urls = sorted(u for u in candidates_http if is_valid_riverscene_event_url(u))
            stats["unique_candidates_before_rules"] = len(candidates_http)

    stats["filtered_urls_kept"] = len(urls)

    if len(urls) > _MAX_DISCOVERED_URLS:
        urls = urls[:_MAX_DISCOVERED_URLS]
        stats["filtered_urls_kept"] = len(urls)

    logger.info(
        "RiverScene calendar discovery (markup): raw=%s filtered=%s unique_candidates=%s playwright=%s",
        stats["raw_urls_found"],
        stats["filtered_urls_kept"],
        stats["unique_candidates_before_rules"],
        stats["playwright_used"],
    )
    return urls, stats
