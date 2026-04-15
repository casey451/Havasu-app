"""Rules for which raw calendar **event** payloads may appear on homepage-style lists (/today, /week)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def include_in_homepage_calendar_lists(raw_event_payload: dict[str, Any]) -> bool:
    """
    Prefer missing data over wrong data on the homepage.

    * Every source: require a usable **start_date** (undated events never appear in /today or /week).
    * **riverscene** only: also require **riverscene_date_confidence** in ``medium`` or ``high``.
      Missing, empty, ``low``, or ``none`` → excluded (legacy noisy rows until re-crawl).
    """
    start = _parse_iso_date(raw_event_payload.get("start_date"))
    if start is None:
        return False

    src = str(raw_event_payload.get("source") or "").strip().lower()
    if src != "riverscene":
        return True

    conf = raw_event_payload.get("riverscene_date_confidence")
    if conf is None:
        return False
    c = str(conf).strip().lower()
    if c in ("", "low", "none"):
        return False
    return c in ("medium", "high")
