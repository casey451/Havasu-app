"""
Query expansion for vague / weak-intent searches before ranking.

Static EXPANSIONS always available. Optional OpenAI (gpt-4o-mini) when USE_AI_EXPANSION=1.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from core.search_rank import is_discovery_query

logger = logging.getLogger(__name__)

EXPANSIONS: dict[str, list[str]] = {
    "date": ["dinner", "restaurants", "nightlife"],
    "date night": ["dinner", "nightlife", "events"],
    "fun": ["events", "things to do", "activities"],
    "kids": ["kids events", "family", "activities"],
    "party": ["nightlife", "dj", "bar", "events"],
    "food": ["restaurants", "dining", "places to eat"],
    "plumber": ["plumbing", "hvac", "repair"],
}

_MAX_AI_PHRASES = 5
_MAX_TOTAL_PHRASES = 6


def _use_ai_expansion() -> bool:
    return os.getenv("USE_AI_EXPANSION", "").strip() == "1"


def should_expand(intent: dict[str, Any], query: str) -> bool:
    q = query.strip().lower()
    return (
        float(intent.get("confidence") or 0.0) < 0.6
        or len(q.split()) <= 4
        or is_discovery_query(intent, q)
    )


def _expand_query_static(query: str) -> list[str]:
    q0 = query.strip()
    q = q0.lower()
    expanded: set[str] = {q}
    for key, values in EXPANSIONS.items():
        if key in q:
            expanded.update(v.lower() for v in values)
    return list(expanded)


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", t, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def _merge_ai_phrases(original: str, parsed: list[Any]) -> list[str]:
    """Original query first, then up to _MAX_AI_PHRASES unique short phrases; cap total length."""
    base = original.strip().lower()
    out: list[str] = []
    seen: set[str] = set()
    if base:
        out.append(base)
        seen.add(base)
    n = 0
    for x in parsed:
        if n >= _MAX_AI_PHRASES or len(out) >= _MAX_TOTAL_PHRASES:
            break
        if not isinstance(x, str):
            continue
        s = " ".join(x.strip().lower().split())
        if len(s) < 2 or s in seen:
            continue
        out.append(s)
        seen.add(s)
        n += 1
    return out[:_MAX_TOTAL_PHRASES]


def ai_expand_query(query: str) -> list[str]:
    """
    Optional OpenAI expansion. On any failure or missing package, uses static EXPANSIONS.
    """
    q0 = query.strip()
    if not q0:
        return []
    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError:
        logger.info("openai package not installed; using static query expansion")
        return _expand_query_static(q0)

    try:
        client = OpenAI()
        prompt = f"""
Expand this search query into {_MAX_AI_PHRASES} related short search phrases.
Query: "{q0}"
Rules:
- Keep phrases short (1-3 words)
- Focus on local events, businesses, activities
- No explanations
- Return ONLY a JSON array of strings, e.g. ["dinner", "restaurants", "nightlife"]
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        text = (response.choices[0].message.content or "").strip()
        text = _strip_json_fence(text)
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            return _expand_query_static(q0)
        merged = _merge_ai_phrases(q0, parsed)
        if not merged:
            return _expand_query_static(q0)
        # Dedupe preserving order
        seen: set[str] = set()
        final: list[str] = []
        for p in merged:
            if p not in seen:
                seen.add(p)
                final.append(p)
        return final[:_MAX_TOTAL_PHRASES]
    except Exception as exc:
        logger.warning("AI query expansion failed; using static map: %s", exc)
        return _expand_query_static(q0)


def expand_query(query: str) -> list[str]:
    if _use_ai_expansion():
        return ai_expand_query(query)
    return _expand_query_static(query)


def raw_payload_dedupe_key(raw: dict[str, Any]) -> str:
    """Stable id for crawler + user event payloads."""
    uid = raw.get("user_event_id")
    if uid is not None:
        return f"u-{int(uid)}"
    iid = raw.get("item_db_id")
    if iid is not None:
        return f"c-{int(iid)}"
    su = str(raw.get("source_url") or "")
    ti = str(raw.get("title") or "")
    return f"url:{su}|t:{ti}"


def match_rows_for_queries(rows: list[dict[str, Any]], expanded_queries: list[str]) -> list[dict[str, Any]]:
    """Substring match against title+description+tags; dedupe while preserving order."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for eq in expanded_queries:
        eq_lower = eq.strip().lower()
        for r in rows:
            tags = r.get("tags")
            tag_text = " ".join(str(t) for t in tags) if isinstance(tags, list) else ""
            search_blob = f"{r.get('title') or ''} {r.get('description') or ''} {tag_text}".lower()
            if eq_lower and eq_lower in search_blob:
                k = raw_payload_dedupe_key(r)
                if k not in seen:
                    seen.add(k)
                    out.append(r)
    return out
