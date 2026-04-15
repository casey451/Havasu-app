"""
PHASE 1 — Intent mapping from free-text queries (deterministic, no AI).

Maps user queries to suggested tags and a primary category for ranking/boosting later.
"""
from __future__ import annotations

# Category key → keywords / synonyms (order: longer phrases before short tokens where useful).
INTENT_KEYWORDS: dict[str, list[str]] = {
    "hvac": [
        "air conditioning",
        "air conditioner",
        "heat pump",
        "furnace",
        "heating",
        "cooling",
        "hvac",
        "a/c",
    ],
    "plumbing": [
        "plumbing",
        "plumber",
        "water heater",
        "drain",
        "pipe",
        "leak",
        "toilet",
        "sink",
    ],
    "electrical": [
        "electrical",
        "electrician",
        "wiring",
        "breaker",
        "outlet",
        "lighting",
    ],
    "food": [
        "restaurant",
        "breakfast",
        "brunch",
        "lunch",
        "dinner",
        "cafe",
        "coffee",
        "food",
        "dining",
        "eat",
        "pizza",
        "burger",
    ],
    "nightlife": [
        "nightlife",
        "night life",
        "bar",
        "pub",
        "club",
        "late night",
        "cocktail",
        "dj",
        "drinks",
    ],
    "kids": [
        "kids",
        "children",
        "child",
        "family",
        "toddler",
        "youth",
        "playground",
        "daycare",
    ],
    "sports": [
        "sports",
        "sport",
        "marathon",
        "5k",
        "10k",
        "race",
        "run",
        "soccer",
        "basketball",
        "gym",
        "fitness",
        "yoga",
        "game",
    ],
    "events": [
        "events",
        "event",
        "festival",
        "concert",
        "show",
        "things to do",
        "weekend",
        "entertainment",
        "live music",
    ],
}


def _count_matches(query_lower: str, keywords: list[str]) -> int:
    """Count how many listed keywords appear as substrings (each keyword at most once)."""
    n = 0
    for kw in keywords:
        if len(kw) < 2:
            continue
        if kw in query_lower:
            n += 1
    return n


def parse_intent(query: str) -> dict:
    """
    Parse a user query into intent hints.

    Returns:
        {
            "tags": list[str],       # category keys that had at least one keyword hit
            "category": str | None,  # strongest single category, if any
            "confidence": float,     # 0–1, higher when more keyword evidence
        }
    """
    q = (query or "").strip().lower()
    if not q:
        return {"tags": [], "category": None, "confidence": 0.0}

    scores: dict[str, int] = {}
    total_hits = 0
    for cat, keywords in INTENT_KEYWORDS.items():
        n = _count_matches(q, keywords)
        if n > 0:
            scores[cat] = n
            total_hits += n

    if not scores:
        return {"tags": [], "category": None, "confidence": 0.08}

    # Tags: all categories with any match, highest score first then name
    tags = sorted(scores.keys(), key=lambda c: (-scores[c], c))

    # Primary category: highest score; tie → lexicographically smallest key
    max_score = max(scores.values())
    tied = [c for c, s in scores.items() if s == max_score]
    category = sorted(tied)[0]

    # Confidence: more hits → higher, capped at 1.0; floor when we have any match
    raw = 0.25 + 0.12 * total_hits + 0.05 * len(scores)
    confidence = min(1.0, raw)

    return {"tags": tags, "category": category, "confidence": round(confidence, 4)}
