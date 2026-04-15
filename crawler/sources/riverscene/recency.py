from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().split("T")[0]).date()
        except ValueError:
            return None
    return None


def is_riverscene_event_recent(
    parsed: dict[str, Any],
    *,
    today: date | None = None,
    max_past_days: int = 30,
) -> bool:
    """
    Keep events whose last day (end_date, else start_date) is not before (today - max_past_days).

    Undated events are kept (cannot apply the rule).
    """
    today = today or date.today()
    cutoff = today - timedelta(days=max_past_days)

    end = _coerce_date(parsed.get("end_date"))
    start = _coerce_date(parsed.get("start_date"))
    last = end or start
    if last is None:
        return True

    return last >= cutoff
