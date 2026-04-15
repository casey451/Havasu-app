"""Starter taxonomy: map free-text `category` into one of five top-level groups."""
from __future__ import annotations

import re

# Display names for AI / browse — businesses store `category_group` as one of these.
CATEGORY_GROUPS: tuple[str, ...] = (
    "Home Services",
    "Food & Drink",
    "Fitness",
    "Kids Activities",
    "Events & Entertainment",
)

_GROUP_SET_LOWER = {g.lower() for g in CATEGORY_GROUPS}


def resolve_category_group(category: str) -> str:
    """
    Map user-provided category (e.g. 'HVAC', 'breakfast') to a single starter group.
    Accepts exact group name (case-insensitive) or keyword heuristics.
    """
    raw = (category or "").strip()
    if not raw:
        return ""

    if raw.lower() in _GROUP_SET_LOWER:
        for g in CATEGORY_GROUPS:
            if g.lower() == raw.lower():
                return g

    blob = raw.lower()

    if re.search(
        r"\b(hvac|plumb|electric|electrical|roof|contractor|handyman|"
        r"landscap|pest|locksmith|appliance|repair)\b",
        blob,
    ):
        return "Home Services"

    if re.search(
        r"\b(food|drink|restaurant|cafe|coffee|bar|brew|breakfast|lunch|dinner|"
        r"kitchen|diner|pizza|taco)\b",
        blob,
    ):
        return "Food & Drink"

    if re.search(
        r"\b(gym|fitness|yoga|pilates|crossfit|workout|personal train|cycle|spin)\b",
        blob,
    ):
        return "Fitness"

    if re.search(
        r"\b(kids|children|child|family fun|daycare|play|youth|toddler|teen)\b",
        blob,
    ):
        return "Kids Activities"

    if re.search(
        r"\b(event|entertainment|venue|music|theater|theatre|show|festival|nightlife)\b",
        blob,
    ):
        return "Events & Entertainment"

    # Default bucket for local services not caught above
    return "Events & Entertainment"
