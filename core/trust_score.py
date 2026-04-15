"""Source trust 0–1 for ranking / future recommendations (computed at normalize time)."""
from __future__ import annotations

from typing import Any


def compute_trust_score(payload: dict[str, Any]) -> float:
    """
    user/business-submitted → 1.0
    RiverScene: high 0.7, medium 0.5, else 0.2
    Other crawlers: high_confidence True → 0.7, else 0.5
    """
    src = str(payload.get("source") or "").strip().lower()
    if src == "user":
        return 1.0

    if src == "riverscene":
        rc = str(payload.get("riverscene_date_confidence") or "").strip().lower()
        if rc == "high":
            return 0.7
        if rc == "medium":
            return 0.5
        return 0.2

    if payload.get("high_confidence") is True:
        return 0.7
    return 0.5
