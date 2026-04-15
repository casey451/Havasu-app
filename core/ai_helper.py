"""
Cheap AI fallback hook: only suggest when intent is weak or results are empty.

Replace `generate_suggestions` with an API-backed implementation later; keep `should_use_ai`
to control cost.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_SUGGESTIONS = 3

# Empty-index / weak-match copy (no external API).
_EMPTY_NO_CATEGORY: list[str] = [
    "No listings matched that search yet",
    "Try different words or browse upcoming events",
    "Check back as new businesses and events are added",
]

_EMPTY_BY_CATEGORY: dict[str, list[str]] = {
    "plumbing": [
        "No plumbers found yet",
        "Try checking back later",
        "Or browse other local services",
    ],
    "hvac": [
        "No HVAC listings matched yet",
        "Try checking back later",
        "Or browse other local services",
    ],
    "electrical": [
        "No electricians found yet",
        "Try checking back later",
        "Or browse other local services",
    ],
    "food": [
        "No food or dining listings matched yet",
        "Try restaurants, dinner, or brunch in your search",
        "Or browse events happening this week",
    ],
    "events": [
        "No events matched that exact search",
        "Try “this weekend” or a type of event you want",
        "New listings are added often—check back soon",
    ],
    "kids": [
        "No kid-focused listings matched yet",
        "Try family, playground, or a day of the week",
        "Or browse all upcoming events",
    ],
    "nightlife": [
        "No nightlife listings matched yet",
        "Try bar, live music, or tonight",
        "Or browse upcoming events",
    ],
    "sports": [
        "No sports listings matched yet",
        "Try race, 5k, or a sport name",
        "Or browse community events",
    ],
}

_REFINE_LOW_CONF: list[str] = [
    "Try a shorter or more specific phrase",
    "Browse the calendar for what's on nearby",
    "Adjust your search and try again",
]


def fallback_generic_suggestions() -> list[str]:
    """Stable copy when suggestion parsing fails."""
    return list(_EMPTY_NO_CATEGORY[:_MAX_SUGGESTIONS])


def should_use_ai(results: list[Any], intent: dict[str, Any]) -> bool:
    if len(results) == 0:
        return True
    if float(intent.get("confidence") or 0.0) < 0.2:
        return True
    return False


def _safe_results_len(results: list[Any]) -> int:
    if not isinstance(results, list):
        return 0
    return len(results)


def generate_suggestions(
    query: str,
    intent: dict[str, Any],
    results: list[Any],
) -> dict[str, list[str]]:
    """
    Deterministic copy for empty or weak-intent searches. Never assumes rows are businesses.
    """
    try:
        q = (query or "").strip()
        cat = (intent.get("category") or "").lower()
        n = _safe_results_len(results)

        if n == 0:
            if cat and cat in _EMPTY_BY_CATEGORY:
                return {"suggestions": _EMPTY_BY_CATEGORY[cat][:_MAX_SUGGESTIONS]}
            _ = q
            return {"suggestions": _EMPTY_NO_CATEGORY[:_MAX_SUGGESTIONS]}

        # Has results but low confidence: gentle refinement only.
        suggestions: list[str] = []
        if cat == "food":
            suggestions = [
                "Try adding breakfast, lunch, or dinner",
                "Include a cuisine or neighborhood if you can",
                "Browse the calendar for food-related events",
            ]
        elif cat == "events":
            suggestions = [
                "Add a day or “this weekend” to narrow results",
                "Try concert, festival, or kids for more ideas",
                "Scroll the list—ranking favors what fits your search",
            ]
        elif cat == "kids":
            suggestions = [
                "Try family, playground, or a weekday",
                "Include an activity like sports or crafts",
                "Browse all upcoming events for more options",
            ]
        else:
            suggestions = list(_REFINE_LOW_CONF)

        return {"suggestions": suggestions[:_MAX_SUGGESTIONS]}
    except Exception as exc:
        logger.warning("generate_suggestions fallback: %s", exc)
        return {"suggestions": _EMPTY_NO_CATEGORY[:_MAX_SUGGESTIONS]}
