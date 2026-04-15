from __future__ import annotations

import json
import logging
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from core.http import build_client


logger = logging.getLogger(__name__)

BASE_EVENTS_URL = "https://www.golakehavasu.com/events/"
ANNUAL_CALENDAR_URL = "https://www.golakehavasu.com/events/annual-event-calendar/"

SEED_LISTING_URLS = [
    BASE_EVENTS_URL,
    ANNUAL_CALENDAR_URL,
]

_EXCLUDED_PATH_PREFIXES = (
    "/events/submit-an-event",
    "/events/event-sponsorships",
)

_BLOCKED_SECOND_SEGMENTS = frozenset(
    {
        "submit-an-event",
        "event-sponsorships",
        "annual-event-calendar",
    }
)

_MAX_LISTING_PAGES = 10
_MAX_EVENT_URLS = 75
_MAX_SECONDARY_HUB_CRAWLS = 25


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean = parsed._replace(query="", fragment="")
    path = clean.path or "/"
    if not path.endswith("/"):
        path = f"{path}/"
    clean = clean._replace(path=path)
    return urlunparse(clean)


def _path_parts(url: str) -> list[str]:
    path = urlparse(url).path.rstrip("/")
    return [p for p in path.split("/") if p]


def _path_segment_lower(url: str) -> list[str]:
    return [p.lower() for p in _path_parts(url)]


def is_candidate_event_url(url: str) -> bool:
    """
    Likely event detail page under /events/ — relaxed depth; excludes hubs, listings, taxonomies.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.netloc.lower()
    if host not in ("www.golakehavasu.com", "golakehavasu.com"):
        return False

    path = parsed.path or "/"
    if not path.startswith("/events/"):
        return False

    # Bare /events/ listing — never a detail page (path "/events" or "/events/" only).
    parts_only = [p for p in path.rstrip("/").split("/") if p]
    if len(parts_only) == 1 and parts_only[0].lower() == "events":
        return False

    lower_path = path.lower()
    for prefix in _EXCLUDED_PATH_PREFIXES:
        if lower_path.startswith(prefix):
            return False

    parts = _path_segment_lower(url)
    if len(parts) < 2 or parts[0] != "events":
        return False
    if len(parts) == 1:
        return False

    # Listing pagination
    if len(parts) >= 3 and parts[1] == "page" and parts[2].isdigit():
        return False

    if parts[-1] == "index":
        return False

    # WordPress /events/*/page/N/ (nested pagination)
    if len(parts) >= 2 and parts[-2] == "page" and parts[-1].isdigit():
        return False

    # Taxonomies & archives (crawl elsewhere, not event rows)
    if "category" in parts or "tag" in parts:
        return False
    if "archive" in parts or "archives" in parts:
        return False

    if any(x in parts for x in ("wp-json", "feed", "rss", "author", "attachment")):
        return False

    # Hub pages (no detail slug)
    if len(parts) == 2 and parts[1] in _BLOCKED_SECOND_SEGMENTS:
        return False
    if len(parts) == 2 and parts[1] == "annual-event-calendar":
        return False

    return True


def is_link_hub_or_listing(url: str) -> bool:
    """URLs we may fetch to harvest more /events/ links (not counted as event details)."""
    parsed = urlparse(url)
    if parsed.netloc.lower() not in ("www.golakehavasu.com", "golakehavasu.com"):
        return False
    path = (parsed.path or "/").lower()
    if not path.startswith("/events/"):
        return False
    parts = _path_segment_lower(url)
    if len(parts) <= 1:
        return True
    if len(parts) >= 3 and parts[1] == "page" and parts[2].isdigit():
        return True
    if len(parts) == 2 and parts[1] == "annual-event-calendar":
        return True
    if "category" in parts or "tag" in parts:
        return True
    if "archive" in parts:
        return True
    return False


def _content_region_html(full_soup: BeautifulSoup) -> str | None:
    regions: list = []
    for sel in (
        "main",
        "[role='main']",
        "article",
        ".entry-content",
        ".post-content",
        ".page-content",
        "#content",
        ".content-area",
    ):
        regions.extend(full_soup.select(sel))
    if not regions:
        return None
    return "".join(str(r) for r in regions)


def _walk_json_for_url_strings(obj: object, bucket: set[str]) -> None:
    if isinstance(obj, str):
        if "golakehavasu.com" in obj and "/events/" in obj:
            bucket.add(obj.strip())
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_json_for_url_strings(v, bucket)
    elif isinstance(obj, list):
        for v in obj:
            _walk_json_for_url_strings(v, bucket)


def _harvest_urls_from_ld_json(html: str, page_url: str) -> set[str]:
    """Collect event detail URLs referenced in JSON-LD (not always duplicated as <a> links)."""
    soup = BeautifulSoup(html, "html.parser")
    raw: set[str] = set()
    for script in soup.select('script[type="application/ld+json"]'):
        if not script.string or not script.string.strip():
            continue
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        _walk_json_for_url_strings(data, raw)

    out: set[str] = set()
    for u in raw:
        candidate = canonicalize_url(urljoin(page_url, u))
        if is_candidate_event_url(candidate):
            out.add(candidate)
    return out


def _harvest_event_links_from_soup(soup: BeautifulSoup, page_url: str) -> set[str]:
    out: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(page_url, href)
        candidate = canonicalize_url(absolute)
        if is_candidate_event_url(candidate):
            out.add(candidate)
    return out


def extract_links(
    html: str,
    page_url: str,
    *,
    annual_deep: bool = False,
) -> tuple[set[str], int]:
    """
    Returns (filtered event detail URLs, raw anchor count on full document).
    On annual_deep, union links from main content regions and full page (deeper coverage).
    """
    full_soup = BeautifulSoup(html, "html.parser")
    raw_count = len(full_soup.select("a[href]"))

    discovered: set[str] = set()
    discovered |= _harvest_event_links_from_soup(full_soup, page_url)

    if annual_deep:
        region_html = _content_region_html(full_soup)
        if region_html:
            region_soup = BeautifulSoup(region_html, "html.parser")
            discovered |= _harvest_event_links_from_soup(region_soup, page_url)

    discovered |= _harvest_urls_from_ld_json(html, page_url)

    return discovered, raw_count


def extract_hub_links(html: str, page_url: str) -> set[str]:
    """All same-site /events/ links that may be secondary hubs to crawl."""
    found: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        absolute = canonicalize_url(urljoin(page_url, href))
        if is_link_hub_or_listing(absolute) and not is_candidate_event_url(absolute):
            found.add(absolute)
    return found


def _looks_like_events_listing_url(url: str) -> bool:
    parts = _path_parts(url)
    if not parts or parts[0].lower() != "events":
        return False
    pl = [p.lower() for p in parts]
    if len(pl) == 1:
        return True
    if len(pl) >= 3 and pl[1] == "page" and pl[2].isdigit():
        return True
    return False


def find_next_listing_url(html: str, page_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    link = soup.find("link", attrs={"rel": "next"})
    if link and link.get("href"):
        cand = canonicalize_url(urljoin(page_url, link["href"]))
        if _looks_like_events_listing_url(cand):
            return cand

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        rel = anchor.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        rel_l = [str(r).lower() for r in rel]
        text = _clean_anchor_text(anchor)
        classes = " ".join(anchor.get("class", [])).lower()
        is_next = (
            "next" in rel_l
            or text in ("next", "next page", "older posts", "older")
            or "next" in classes
            or ("pagination" in classes and "next" in text)
        )
        if not is_next:
            continue
        absolute = canonicalize_url(urljoin(page_url, href))
        if "golakehavasu.com" not in absolute.lower():
            continue
        if _looks_like_events_listing_url(absolute):
            return absolute

    return None


def _clean_anchor_text(anchor) -> str:
    return " ".join(anchor.get_text(" ", strip=True).split()).lower()


def _crawl_listing_with_pagination(
    client,
    start_url: str,
    max_pages: int,
    annual_deep: bool,
) -> tuple[set[str], int, int, set[str]]:
    """
    Returns (event_urls, listing_pages_fetched, raw_link_count_sum, hub_links_seen).
    Stops pagination early if a listing page adds no new event URLs.
    """
    collected: set[str] = set()
    hub_from_listings: set[str] = set()
    seen_listing_urls: set[str] = set()
    pages_fetched = 0
    raw_links_total = 0
    current = canonicalize_url(start_url)

    while current and pages_fetched < max_pages:
        if current in seen_listing_urls:
            break
        seen_listing_urls.add(current)

        response = client.get(current)
        response.raise_for_status()
        pages_fetched += 1
        final_url = canonicalize_url(str(response.url))

        before = len(collected)
        page_events, raw_n = extract_links(response.text, final_url, annual_deep=annual_deep)
        raw_links_total += raw_n
        collected.update(page_events)
        hub_from_listings.update(extract_hub_links(response.text, final_url))
        if pages_fetched > 1 and len(collected) == before:
            break

        next_url = find_next_listing_url(response.text, final_url)
        if not next_url:
            break
        next_canon = canonicalize_url(next_url)
        if next_canon in seen_listing_urls:
            break
        current = next_canon

    return collected, pages_fetched, raw_links_total, hub_from_listings


def discover_event_urls() -> list[str]:
    all_urls: set[str] = set()
    pagination_pages = 0
    hub_pages_crawled = 0
    total_raw_links = 0
    hub_queue: set[str] = set()
    hubs_done: set[str] = set()

    with build_client() as client:
        for seed in SEED_LISTING_URLS:
            annual_deep = seed.rstrip("/").endswith("annual-event-calendar")
            found, pages, raw_n, hub_links = _crawl_listing_with_pagination(
                client,
                seed,
                _MAX_LISTING_PAGES,
                annual_deep=annual_deep,
            )
            all_urls.update(found)
            pagination_pages += pages
            total_raw_links += raw_n
            hub_queue.update(hub_links)

        # Secondary hubs (category / tag / archive / calendar index): one GET each
        while hub_queue and hub_pages_crawled < _MAX_SECONDARY_HUB_CRAWLS:
            hub = hub_queue.pop()
            canon = canonicalize_url(hub)
            if canon in hubs_done:
                continue
            hubs_done.add(canon)
            try:
                r = client.get(canon)
                r.raise_for_status()
            except Exception:
                logger.debug("Skipping hub fetch %s", canon, exc_info=True)
                continue
            hub_pages_crawled += 1
            final_u = canonicalize_url(str(r.url))
            ev, raw_n = extract_links(r.text, final_u, annual_deep=False)
            total_raw_links += raw_n
            all_urls.update(ev)
            for h in extract_hub_links(r.text, final_u):
                if canonicalize_url(h) not in hubs_done:
                    hub_queue.add(h)

    sorted_urls = sorted(all_urls)
    filtered_count = len(sorted_urls)
    if len(sorted_urls) > _MAX_EVENT_URLS:
        sorted_urls = sorted_urls[:_MAX_EVENT_URLS]

    pages_total = pagination_pages + hub_pages_crawled

    logger.info(
        "Discovery: pagination_pages=%s hub_pages=%s total_pages=%s raw_links=%s filtered_event_urls=%s (cap=%s)",
        pagination_pages,
        hub_pages_crawled,
        pages_total,
        total_raw_links,
        filtered_count,
        _MAX_EVENT_URLS,
    )
    print(
        f"[discover] listing_pages_crawled={pagination_pages} "
        f"hub_pages_crawled={hub_pages_crawled} "
        f"total_pages_crawled={pages_total} "
        f"raw_links_found={total_raw_links} "
        f"filtered_event_urls={filtered_count} (cap {_MAX_EVENT_URLS})"
    )

    return sorted_urls
