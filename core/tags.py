"""Lightweight keyword → tag hints for events (no ML)."""
from __future__ import annotations

import re


def infer_tags(title: str, description: str) -> list[str]:
    blob = f"{title or ''} {description or ''}".lower()
    tags: set[str] = set()
    if re.search(r"\bkids\b|\bfamily\b|\bchildren\b", blob):
        tags.add("kids")
    if re.search(r"\bmusic\b|\bdj\b|\bconcert\b|\bband\b", blob):
        tags.add("music")
    if re.search(r"\btrivia\b|\bgame\b|\bbingo\b|game night", blob):
        tags.add("social")
    if re.search(r"\brace\b|\brun\b|\bwalk\b|\bsport\b|\bmarathon\b|\b5k\b|\b10k\b", blob):
        tags.add("sports")
    return sorted(tags)
