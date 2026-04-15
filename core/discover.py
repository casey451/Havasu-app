"""Homepage discovery helpers: today, this weekend, and popular."""
from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any


def _parse_row_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def get_fallback_rows() -> list[dict[str, Any]]:
    return [
        {
            "title": "Popular this weekend",
            "description": "Check out local events happening soon",
            "tags": ["events"],
            "category": "events",
            "type": "event",
            "source": "fallback",
            "source_url": "",
            "start_date": "",
            "end_date": "",
            "weekday": "",
            "start_time": "",
            "end_time": "",
            "location_label": "",
            "has_start_time": False,
            "has_end_time": False,
            "has_location": False,
            "trust_score": 0.0,
        }
    ]


def get_today(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _parse_row_date(r.get("start_date"))
        if d is not None and d == today:
            out.append(r)
    return out[:limit]


def get_weekend(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    now = datetime.now(UTC).date()
    days_ahead = 6 - now.weekday()  # until Sunday
    end = now + timedelta(days=max(0, days_ahead))
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _parse_row_date(r.get("start_date"))
        if d is not None and now <= d <= end:
            out.append(r)
    return out[:limit]


def get_popular(rows: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    if rows:
        now = datetime.now(UTC)

        def _as_dt(value: Any) -> datetime | None:
            if not isinstance(value, str):
                return None
            raw = value.strip()
            if not raw:
                return None
            if "T" in raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    return dt.astimezone(UTC)
                except ValueError:
                    return None
            d = _parse_row_date(raw)
            if d is None:
                return None
            return datetime(d.year, d.month, d.day, tzinfo=UTC)

        def _row_start_end(r: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
            start_dt = _as_dt(r.get("start_date"))
            end_dt = _as_dt(r.get("end_date"))
            start_time_raw = str(r.get("start_time") or "").strip()
            end_time_raw = str(r.get("end_time") or "").strip()
            if start_dt and start_time_raw and "T" not in str(r.get("start_date") or ""):
                hh, mm = (start_time_raw + ":00:00").split(":")[:2]
                start_dt = start_dt.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if end_dt and end_time_raw and "T" not in str(r.get("end_date") or ""):
                hh, mm = (end_time_raw + ":00:00").split(":")[:2]
                end_dt = end_dt.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            elif start_dt and end_dt is None:
                # Treat date-only rows as all-day so active-now still behaves.
                end_dt = start_dt + timedelta(hours=23, minutes=59)
            return start_dt, end_dt

        def engagement_score(r: dict[str, Any]) -> float:
            trust = float(r.get("trust_score") or 0.0)
            views = max(0.0, float(r.get("view_count") or 0.0))
            clicks = max(0.0, float(r.get("click_count") or 0.0))
            engagement_raw = 0.12 * math.log1p(views) + 0.2 * math.log1p(clicks)
            start = _parse_row_date(r.get("start_date"))
            if start is None:
                recency = 0.0
            else:
                age_days = (start - now.date()).days
                if age_days > 14:
                    recency = -0.2
                elif 3 <= age_days <= 14:
                    recency = 0.1
                elif 0 <= age_days < 3:
                    recency = 0.3
                elif -3 <= age_days < 0:
                    recency = -0.1
                else:
                    recency = -0.3
            base = trust + recency
            engagement = min(engagement_raw, max(0.0, base * 0.4))
            return base + engagement

        def ranking_fields(r: dict[str, Any]) -> tuple[bool, bool, int, float]:
            start_dt, end_dt = _row_start_end(r)
            is_active_now = bool(start_dt and end_dt and start_dt <= now <= end_dt)
            is_today = bool(start_dt and start_dt.date() == now.date())
            if start_dt is None:
                minutes_until_start = 10**9
            elif start_dt < now and not is_active_now:
                minutes_until_start = 10**8 + int((now - start_dt).total_seconds() // 60)
            else:
                minutes_until_start = max(0, int((start_dt - now).total_seconds() // 60))
            return is_active_now, is_today, minutes_until_start, engagement_score(r)

        # Popular timeline should only include true activity-slot rows.
        candidates = [r for r in rows if str(r.get("activity_id") or "").strip()]
        if not candidates:
            return get_fallback_rows()

        scored = [(r, ranking_fields(r)) for r in candidates]
        ordered_scored = sorted(
            scored,
            key=lambda pair: (
                0 if pair[1][0] else 1,  # active now first
                0 if pair[1][1] else 1,  # then today
                pair[1][2],              # then soonest start
                -pair[1][3],             # then engagement
            ),
        )

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        featured_count = 0
        max_featured = min(3, limit)
        debug_rows: list[tuple[str, str, bool, int]] = []
        for r, fields in ordered_scored:
            key = str(r.get("activity_id") or r.get("id") or r.get("title") or "")
            if key in seen:
                continue
            if bool(r.get("is_featured")):
                if featured_count >= max_featured:
                    continue
                featured_count += 1
            seen.add(key)
            out.append(r)
            is_active_now, _, minutes_until_start, _ = fields
            debug_rows.append(
                (
                    str(r.get("title") or ""),
                    str(r.get("start_date") or ""),
                    is_active_now,
                    minutes_until_start,
                )
            )
            if len(out) >= limit:
                break
        if debug_rows:
            print("DISCOVER_TOP10", debug_rows[:10])
        return out
    return get_fallback_rows()
