from __future__ import annotations

import logging
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.models import validate_event_payload
from core.sources import SOURCE_GOLAKEHAVASU, SOURCE_HAVASU_PARKS, SOURCE_RIVERSCENE
from crawler.sources.golakehavasu.discover import discover_event_urls as discover_golakehavasu_urls
from crawler.sources.golakehavasu.fetch import fetch_and_store_page as fetch_golakehavasu_page
from crawler.sources.golakehavasu.normalize import normalize_event as normalize_golakehavasu_event
from crawler.sources.golakehavasu.parse_events import parse_event_page as parse_golakehavasu_page
from crawler.sources.riverscene.discover import (
    discover_calendar_event_urls,
    is_valid_riverscene_event_url,
)
from crawler.sources.riverscene.fetch import fetch_and_store_page as fetch_riverscene_page
from crawler.sources.riverscene.normalize import normalize_event as normalize_riverscene_event
from crawler.sources.riverscene.parse_events import parse_event_page as parse_riverscene_page
from crawler.sources.riverscene.recency import is_riverscene_event_recent
from crawler.sources.havasu_parks.discover import discover_havasu_parks
from crawler.sources.havasu_parks.fetch import fetch_and_store_page as fetch_havasu_parks_page
from crawler.sources.havasu_parks.normalize import normalize_program_item, normalize_schedule_item
from crawler.sources.havasu_parks.parse_parks_programs import (
    parse_programs_activities_page,
    parse_youth_athletics_programs,
)
from urllib.parse import urlparse

from crawler.sources.havasu_parks.parse_schedule import (
    parse_community_center_schedule,
    parse_open_swim_schedule,
    parse_pickleball_schedule,
)
from crawler.sources.riverscene.validation import (
    compute_event_score,
    compute_high_confidence,
    passes_eligibility_gate,
    passes_final_keep_threshold,
    summarize_score_distribution,
    title_passes_filter,
)
from db.database import (
    crawl_audit_summary,
    delete_items_with_source_urls,
    get_connection,
    init_db,
    run_pre_crawl_cleanup,
    upsert_item,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _read_raw_html(raw_page_id: int) -> tuple[str, str]:
    with get_connection() as conn:
        row = conn.execute("SELECT url, html FROM raw_pages WHERE id = ?", (raw_page_id,)).fetchone()
    if row is None:
        return "", ""
    return str(row["url"]), str(row["html"])


def _run_source(
    source_label: str,
    discover_fn: Callable[[], list[str]],
    fetch_fn: Callable[[str], int],
    parse_fn: Callable[..., dict[str, Any]],
    normalize_fn: Callable[..., dict[str, Any]],
    source_counts: Counter[str],
    skipped_should_store: Counter[str],
) -> tuple[int, int]:
    urls = discover_fn()
    print(f"[crawler] source={source_label} urls_discovered={len(urls)}")
    logger.info("%s: discovered %s URLs", source_label, len(urls))

    success = 0
    failed = 0
    for url in urls:
        try:
            raw_page_id = fetch_fn(url)
            canonical_url, html = _read_raw_html(raw_page_id)
            if not html:
                raise RuntimeError("No raw HTML found after fetch")
            parsed = parse_fn(html, source_url=canonical_url or url)
            normalized = normalize_fn(parsed, source=source_label)
            item_id = upsert_item(payload=normalized, raw_page_id=raw_page_id)
            if item_id is None:
                skipped_should_store[source_label] += 1
                continue
            source_counts[source_label] += 1
            success += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.exception("Failed processing %s (%s): %s", url, source_label, exc)

    print(f"[crawler] source={source_label} processed={success} failed={failed}")
    logger.info("%s: processed=%s failed=%s", source_label, success, failed)
    return success, failed


def _run_riverscene_calendar(
    source_counts: Counter[str], skipped_should_store: Counter[str]
) -> None:
    urls, disc_stats = discover_calendar_event_urls()

    print(f"[crawler] source=riverscene urls_discovered={len(urls)}")
    logger.info("riverscene: discovered %s URLs (after filter)", len(urls))

    valid_kept = 0
    failed = 0
    skipped_stale = 0
    discarded_title = 0
    discarded_ineligible = 0
    discarded_low_score = 0
    total_parsed = 0
    score_distribution: Counter[int] = Counter()

    for url in urls:
        try:
            if not is_valid_riverscene_event_url(url):
                logger.warning("RiverScene skip (not an event URL): %s", url)
                continue
            raw_page_id = fetch_riverscene_page(url, source=SOURCE_RIVERSCENE)
            canonical_url, html = _read_raw_html(raw_page_id)
            if not html:
                raise RuntimeError("No raw HTML found after fetch")
            final_url = (canonical_url or url).strip()
            if not is_valid_riverscene_event_url(final_url):
                logger.warning(
                    "RiverScene skip (final URL not under /events/): %s", final_url
                )
                continue
            parsed = parse_riverscene_page(html, source_url=final_url)
            effective_url = str(parsed.get("source_url") or final_url).strip()
            if not is_valid_riverscene_event_url(effective_url):
                logger.warning(
                    "RiverScene skip (payload URL not a calendar event): %s",
                    effective_url,
                )
                continue
            total_parsed += 1
            if not is_riverscene_event_recent(parsed):
                skipped_stale += 1
                logger.debug("RiverScene skip (not recent): %s", url)
                continue
            if not title_passes_filter(parsed):
                discarded_title += 1
                continue
            if not passes_eligibility_gate(parsed):
                discarded_ineligible += 1
                continue
            score = compute_event_score(parsed)
            score_distribution[score] += 1
            if not passes_final_keep_threshold(parsed, score):
                discarded_low_score += 1
                continue
            normalized = normalize_riverscene_event(parsed, source=SOURCE_RIVERSCENE)
            if compute_high_confidence(parsed):
                normalized = validate_event_payload({**normalized, "high_confidence": True})
            logger.info(
                "riverscene_kept url=%s start_date=%s date_src=%s conf=%s title=%s",
                effective_url,
                normalized.get("start_date"),
                normalized.get("riverscene_date_source"),
                normalized.get("riverscene_date_confidence"),
                (normalized.get("title") or "")[:100],
            )
            item_id = upsert_item(payload=normalized, raw_page_id=raw_page_id)
            if item_id is None:
                skipped_should_store[SOURCE_RIVERSCENE] += 1
                continue
            source_counts[SOURCE_RIVERSCENE] += 1
            valid_kept += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.exception("Failed processing %s (riverscene): %s", url, exc)

    discarded_total = discarded_title + discarded_ineligible + discarded_low_score

    print(
        "[riverscene calendar] "
        f"raw_urls_found={disc_stats.get('raw_urls_found', 0)} "
        f"filtered_urls_kept={disc_stats.get('filtered_urls_kept', len(urls))} "
        f"failed={failed} "
        f"skipped_stale={skipped_stale}"
    )
    print(
        "[riverscene validation] "
        f"total_parsed={total_parsed} "
        f"score_distribution={summarize_score_distribution(score_distribution)} "
        f"kept={valid_kept} "
        f"discarded={discarded_total} "
        f"(bad_title={discarded_title} ineligible_gate={discarded_ineligible} low_score={discarded_low_score} "
        f"skipped_stale={skipped_stale} failed={failed})"
    )
    print(
        f"[crawler] source=riverscene stored={valid_kept} failed={failed} "
        f"skipped_stale={skipped_stale} discarded_validation={discarded_total}"
    )
    logger.info(
        "riverscene: stored=%s failed=%s skipped_stale=%s validation_discarded=%s total_parsed=%s",
        valid_kept,
        failed,
        skipped_stale,
        discarded_total,
        total_parsed,
    )


def _run_havasu_parks(
    source_counts: Counter[str], skipped_should_store: Counter[str]
) -> None:
    urls = discover_havasu_parks()
    print(f"[crawler] source={SOURCE_HAVASU_PARKS} urls_discovered={len(urls)}")
    logger.info("%s: discovered %s URLs", SOURCE_HAVASU_PARKS, len(urls))

    stored = 0
    failed = 0
    for url in urls:
        try:
            raw_page_id = fetch_havasu_parks_page(url, source=SOURCE_HAVASU_PARKS)
            canonical_url, html = _read_raw_html(raw_page_id)
            if not html:
                raise RuntimeError("No raw HTML found after fetch")
            page_url = (canonical_url or url).strip()
            path = urlparse(page_url).path.lower().rstrip("/")
            if path.endswith("/pickleball"):
                rows = parse_pickleball_schedule(html, page_url=page_url)
            elif path.endswith("/community-center"):
                rows = parse_community_center_schedule(html, page_url=page_url)
            elif path.endswith("/youth-athletics"):
                rows = parse_youth_athletics_programs(html, page_url=page_url)
            elif path.endswith("/programs-activities"):
                rows = parse_programs_activities_page(html, page_url=page_url)
            else:
                rows = parse_open_swim_schedule(html, page_url=page_url)

            if not rows:
                logger.warning(
                    "havasu_parks: no rows parsed from %s (page may have changed)",
                    page_url,
                )
            for parsed in rows:
                if parsed.get("type") == "program":
                    normalized = normalize_program_item(parsed, source=SOURCE_HAVASU_PARKS)
                else:
                    normalized = normalize_schedule_item(parsed, source=SOURCE_HAVASU_PARKS)
                item_id = upsert_item(payload=normalized, raw_page_id=raw_page_id)
                if item_id is None:
                    skipped_should_store[SOURCE_HAVASU_PARKS] += 1
                    continue
                source_counts[SOURCE_HAVASU_PARKS] += 1
                stored += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.exception("Failed processing %s (havasu_parks): %s", url, exc)

    print(f"[crawler] source=havasu_parks stored={stored} failed={failed}")
    logger.info("havasu_parks: stored=%s failed=%s", stored, failed)


def run() -> None:
    init_db()
    run_pre_crawl_cleanup()

    # Extra hub cleanup (title-based) if a row slipped past URL filters.
    delete_items_with_source_urls(
        source=SOURCE_GOLAKEHAVASU,
        urls=(
            "https://www.golakehavasu.com/events/",
            "https://www.golakehavasu.com/events",
            "http://www.golakehavasu.com/events/",
            "http://www.golakehavasu.com/events",
        ),
    )
    with get_connection() as _conn:
        _conn.execute(
            """
            DELETE FROM items
            WHERE source = ? AND type = 'event'
              AND json_extract(payload_json, '$.title') = 'Events'
              AND (
                source_url = 'https://www.golakehavasu.com/events/'
                OR source_url = 'https://www.golakehavasu.com/events'
              )
            """,
            (SOURCE_GOLAKEHAVASU,),
        )
        _conn.commit()

    source_counts: Counter[str] = Counter()
    skipped_should_store: Counter[str] = Counter()

    _run_source(
        SOURCE_GOLAKEHAVASU,
        discover_golakehavasu_urls,
        lambda u: fetch_golakehavasu_page(u, source=SOURCE_GOLAKEHAVASU),
        parse_golakehavasu_page,
        normalize_golakehavasu_event,
        source_counts,
        skipped_should_store,
    )

    _run_riverscene_calendar(source_counts, skipped_should_store)

    _run_havasu_parks(source_counts, skipped_should_store)

    print(f"[sources] {dict(source_counts)}")
    print(f"[crawler] skipped_should_store={dict(skipped_should_store)}")

    audit = crawl_audit_summary()
    print("[crawler audit] count_by_source", audit["count_by_source"])
    print("[crawler audit] count_by_type", audit["count_by_type"])
    print("[crawler audit] events_missing_start_date", audit["events_missing_start_date"])
    print("[crawler audit] golake_listing_hub_rows", audit["golake_listing_hub_rows"])
    print(
        "[crawler audit] events_source_url_like_pct_events",
        audit["events_source_url_like_pct_events"],
    )
    dup = audit["duplicate_recurring_groups"]
    print(f"[crawler audit] duplicate_recurring_groups={len(dup)}")
    if dup:
        for row in dup[:20]:
            print("  ", dict(row))
        if len(dup) > 20:
            print(f"  ... and {len(dup) - 20} more")


if __name__ == "__main__":
    run()
