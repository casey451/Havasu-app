"""
PHASE 2 — Boost layer for /search: intent-aware ranking on top of trust_score.

Does not change crawlers, DB, or normalization; only re-orders search results.
"""
from __future__ import annotations

import math
import os
from datetime import UTC, date, datetime
from typing import Any

from core.intent_map import INTENT_KEYWORDS
from core.serialize import expand_merged, finalize_api_list, normalize_item, normalized_sort_tuple

_DISCOVERY_PHRASES: tuple[str, ...] = (
    "things to do",
    "what's happening",
    "whats happening",
    "events",
    "this weekend",
    "today",
    "tonight",
)


def is_discovery_query(intent: dict[str, Any], query: str) -> bool:
    """
    Broad “what’s on / discovery” queries — prefer calendar-style listings over business-posted rows.
    """
    q = (query or "").strip().lower()
    if any(phrase in q for phrase in _DISCOVERY_PHRASES):
        return True
    cat = (intent.get("category") or "").lower()
    return cat in ("events", "social")


def _parse_event_date(item: dict[str, Any]) -> date | None:
    sd = item.get("start_date")
    if not isinstance(sd, str) or len(sd) < 10:
        return None
    try:
        return date.fromisoformat(sd.strip()[:10])
    except ValueError:
        return None


def _is_active_featured(item: dict[str, Any], *, now: datetime) -> bool:
    if not bool(item.get("is_featured")):
        return False
    fu = str(item.get("featured_until") or "").strip()
    if not fu:
        return True
    try:
        dt = datetime.fromisoformat(fu.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt > now
    except ValueError:
        return False


def _engagement_boost(item: dict[str, Any], *, base_plus_relevance: float) -> float:
    """
    Diminishing-return popularity using log scale.
    Cap to <=40% of relevance+base so counts cannot dominate intent match quality.
    """
    try:
        views = max(0.0, float(item.get("view_count") or 0.0))
    except (TypeError, ValueError):
        views = 0.0
    try:
        clicks = max(0.0, float(item.get("click_count") or 0.0))
    except (TypeError, ValueError):
        clicks = 0.0
    raw = 0.12 * math.log1p(views) + 0.2 * math.log1p(clicks)
    cap = max(0.0, base_plus_relevance * 0.4)
    return min(raw, cap)


def score_item(item: dict[str, Any], intent: dict[str, Any], *, query: str = "") -> float:
    """
    Higher = better rank. Uses trust_score as base, then additive boosts, then confidence multiplier.

    Title boost: +0.2 when a keyword from any matched intent category appears in the title
    (avoids a uniform boost for all title matches).

    Discovery queries: boost non-user (crawler) calendar rows; slight penalty for user-posted rows.
    """
    base = float(item.get("trust_score") or 0.0)
    relevance_boost = 0.0

    intent_tags = intent.get("tags") or []
    it_set = {str(x).lower() for x in intent_tags}
    raw_item_tags = item.get("tags") or []
    mt_set = {str(x).lower() for x in raw_item_tags if isinstance(x, str)}
    if it_set and mt_set and (it_set & mt_set):
        relevance_boost += 0.4

    ic = (intent.get("category") or "").lower()
    cat_s = (item.get("category") or "").lower()
    bc_s = (item.get("business_category") or "").lower()
    category_match = False
    if ic:
        if ic == cat_s or ic == bc_s:
            category_match = True
        elif ic in cat_s or (bc_s and ic in bc_s):
            category_match = True
        elif (cat_s and cat_s in ic) or (bc_s and bc_s in ic):
            category_match = True
    if category_match:
        relevance_boost += 0.3

    title_lower = (item.get("title") or "").lower()
    desc_lower = (item.get("description") or "").lower()
    tags_raw = item.get("tags") or []
    tag_tokens: set[str] = set()
    if isinstance(tags_raw, list):
        for t in tags_raw:
            if not isinstance(t, str):
                continue
            tl = t.lower().strip()
            if not tl:
                continue
            tag_tokens.add(tl)
            tag_tokens.update(x for x in tl.split() if x)

    query_l = (query or "").strip().lower()
    if query_l and query_l in title_lower:
        relevance_boost += 0.4
    for word in query_l.split():
        if len(word) < 2:
            continue
        if word in title_lower:
            relevance_boost += 0.1
        if word in tag_tokens:
            relevance_boost += 0.15
        elif word in desc_lower:
            relevance_boost += 0.08
    title_kw_boost = False
    for tag in intent_tags:
        tkey = str(tag).lower()
        if tkey not in INTENT_KEYWORDS:
            continue
        for kw in INTENT_KEYWORDS[tkey]:
            if len(kw) >= 3 and kw in title_lower:
                title_kw_boost = True
                break
        if title_kw_boost:
            break
    if title_kw_boost:
        relevance_boost += 0.2

    ev_date = _parse_event_date(item)
    today = datetime.now(UTC).date()
    if ev_date is not None:
        event_dt = datetime.combine(ev_date, datetime.min.time(), tzinfo=UTC)
        age_hours = (event_dt - datetime.now(UTC)).total_seconds() / 3600.0
        if 24 < age_hours <= 72:
            relevance_boost += 0.5
        elif 72 < age_hours <= 168:
            relevance_boost += 0.3
        elif 0 <= age_hours <= 24:
            relevance_boost += 0.2
        elif 168 < age_hours <= 504:
            relevance_boost += 0.1
        elif age_hours > 504:
            relevance_boost -= 0.2
        elif -24 <= age_hours < 0:
            relevance_boost -= 0.1
        elif -168 <= age_hours < -24:
            relevance_boost -= 0.2
        else:
            relevance_boost -= 0.5

    if item.get("source") == "user" and category_match:
        relevance_boost += 0.2

    # Broad discovery: calendar / crawler listings over business-submitted rows (same type="event" in API).
    if is_discovery_query(intent, query):
        if (item.get("type") or "event").lower() in ("event", "recurring", "program"):
            if item.get("source") != "user":
                relevance_boost += 0.5
            else:
                relevance_boost -= 0.2

    if ic in ("events", "social") and (item.get("type") or "").lower() == "event":
        relevance_boost += 0.2

    if item.get("source") == "fallback":
        relevance_boost -= 1.0

    now_dt = datetime.now(UTC)
    if _is_active_featured(item, now=now_dt):
        relevance_boost += 0.4

    if not str(item.get("title") or "").strip():
        relevance_boost -= 0.5
    has_tags = isinstance(item.get("tags"), list) and len(item.get("tags") or []) > 0
    has_desc = bool(str(item.get("description") or "").strip())
    if not has_tags and not has_desc:
        relevance_boost -= 0.2

    popularity_boost = _engagement_boost(item, base_plus_relevance=(base + relevance_boost))
    boost = relevance_boost + popularity_boost

    conf = float(intent.get("confidence") or 0.0)
    final = (base + boost) * (1.0 + conf)
    if os.getenv("HAVASU_RANK_DEBUG", "").strip() == "1":
        print(
            {
                "title": item.get("title"),
                "views": item.get("view_count"),
                "clicks": item.get("click_count"),
                "start_date": item.get("start_date"),
                "score": float(final),
            }
        )
    return float(final)


def rank_search_results(
    raw_rows: list[dict[str, Any]],
    query_raw: str,
    intent: dict[str, Any],
    expand: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Re-rank title-matched rows using intent boosts, or preserve default order when confidence is low.
    """
    if not raw_rows:
        return []

    if float(intent.get("confidence") or 0.0) < 0.15:
        return finalize_api_list(raw_rows, expand)[:limit]

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = [
        (r, normalize_item(r)) for r in raw_rows
    ]

    qraw = query_raw.strip()

    def sort_key(p: tuple[dict[str, Any], dict[str, Any]]) -> tuple[float, tuple[str, str, str]]:
        _, norm = p
        sc = score_item(norm, intent, query=qraw)
        return (-sc, normalized_sort_tuple(norm))

    pairs.sort(key=sort_key)
    if expand:
        out = [expand_merged(raw, norm) for raw, norm in pairs]
    else:
        out = [norm for _, norm in pairs]
    return out[:limit]
