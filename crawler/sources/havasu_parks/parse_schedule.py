from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from collections.abc import Callable
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

_HAS_CLOCK = re.compile(r"\d{1,2}:\d{2}")
_TIME_RANGE_LIKE = re.compile(
    r"\d{1,2}:\d{2}\s*(?:am|pm)?\s*[-–]\s*.+",
    re.IGNORECASE,
)
# "APRIL 14" style line after a day header
_CAL_DATE_LINE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d",
    re.I,
)

_DAY_NAMES = frozenset(
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
)


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return s[:48] or "row"


def stable_recurring_slot_url(
    page_url: str,
    frag_prefix: str,
    weekday: str | None,
    title: str,
    start_t: str,
    end_t: str,
) -> str:
    """Deterministic fragment so re-crawls upsert the same row (no duplicate slots)."""
    base = page_url.split("#")[0].rstrip("/")
    wd = (weekday or "day").lower()[:3]
    slug = _slugify(title)
    return f"{base}#{frag_prefix}-{wd}-{slug}-{start_t}-{end_t}"


def _weekday_from_header(line: str) -> str | None:
    w = line.strip().lower().rstrip(":").strip()
    if w in _DAY_NAMES:
        return line.strip().title()
    return None


def _is_calendar_date_line(line: str) -> bool:
    return bool(_CAL_DATE_LINE.match(line.strip()))


# Full-line "April 14" (pickleball page uses calendar dates, not MONDAY headers).
_PB_MONTH_DAY = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})$",
    re.I,
)

_PICKLEBALL_TITLE_KEYS = ("pickleball", "open play", "drop in", "court")


def _pickleball_title_allowed(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in _PICKLEBALL_TITLE_KEYS)


def _weekday_for_month_day_line(line: str, year: int) -> str | None:
    m = _PB_MONTH_DAY.match(line.strip())
    if not m:
        return None
    month_name = m.group(1).title()
    day = int(m.group(2))
    months = list(calendar.month_name)
    try:
        month_i = months.index(month_name)
    except ValueError:
        return None
    try:
        d = date(year, month_i, day)
    except ValueError:
        return None
    return d.strftime("%A")


def parse_time_range_line(line: str) -> tuple[str | None, str | None]:
    """Turn '5:00 am - 7:45 am' into 24h '05:00', '07:45'."""
    line = line.strip()
    if not line:
        return None, None
    parts = re.split(r"\s*[-–]\s*", line, maxsplit=1)
    if len(parts) != 2:
        return None, None
    left, right = parts[0].strip(), parts[1].strip()
    try:
        t1 = date_parser.parse(left, fuzzy=True)
        t2 = date_parser.parse(right, fuzzy=True)
        return t1.strftime("%H:%M"), t2.strftime("%H:%M")
    except (ValueError, OverflowError, TypeError):
        return None, None


def _split_day_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split nav preamble, then (weekday, lines until next weekday)."""
    first = None
    for idx, line in enumerate(lines):
        if _weekday_from_header(line):
            first = idx
            break
    if first is None:
        return []

    sections: list[tuple[str, list[str]]] = []
    i = first
    while i < len(lines):
        wd = _weekday_from_header(lines[i])
        if wd is None:
            i += 1
            continue
        buf: list[str] = []
        i += 1
        while i < len(lines) and _weekday_from_header(lines[i]) is None:
            buf.append(lines[i])
            i += 1
        sections.append((wd, buf))
    return sections


def _parse_day_buffer(
    weekday: str,
    buf: list[str],
    *,
    page_url: str,
    location_label: str,
    frag_prefix: str,
) -> list[dict[str, Any]]:
    """Activity / time pairs for one weekday block (open swim: Mon–Sun headers)."""
    if weekday == "Sunday":
        return []

    out: list[dict[str, Any]] = []
    j = 0

    while j < len(buf):
        line = buf[j].strip()
        if not line:
            j += 1
            continue
        if _is_calendar_date_line(line):
            j += 1
            continue

        low = line.lower()
        if "pool closed" in low:
            j += 2 if j + 1 < len(buf) else 1
            continue
        if "not open to the public" in low:
            j += 2 if j + 1 < len(buf) else 1
            continue

        if j + 1 >= len(buf):
            j += 1
            continue

        nxt = buf[j + 1].strip()
        if not _HAS_CLOCK.search(nxt):
            j += 1
            continue
        if not _TIME_RANGE_LIKE.search(nxt):
            j += 1
            continue

        start_t, end_t = parse_time_range_line(nxt)
        if not (start_t and end_t):
            j += 2
            continue

        source_url = stable_recurring_slot_url(
            page_url, frag_prefix, weekday, line, start_t, end_t
        )

        out.append(
            {
                "title": line,
                "weekday": weekday,
                "start_time": start_t,
                "end_time": end_t,
                "has_time": True,
                "location_label": location_label,
                "type": "recurring",
                "source_url": source_url,
                "description": None,
            }
        )
        j += 2

    return out


def parse_open_swim_schedule(html: str, *, page_url: str) -> list[dict[str, Any]]:
    """
    Full-week aquatic schedule from the Open Swim Schedule page (Mon–Sun headers,
    activity + time pairs). Skips private / closed rows and the Sunday block.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    sections = _split_day_sections(lines)
    all_rows: list[dict[str, Any]] = []

    for weekday, buf in sections:
        if not weekday or not str(weekday).strip():
            continue
        wd = str(weekday).strip()
        all_rows.extend(
            _parse_day_buffer(
                wd,
                buf,
                page_url=page_url,
                location_label="Aquatic Center",
                frag_prefix="oss",
            )
        )

    return _dedupe_schedule_rows(all_rows)


def _parse_calendar_date_activity_schedule(
    html: str,
    *,
    page_url: str,
    title_allowed: Callable[[str], bool],
    location_label: str,
    frag_prefix: str,
    max_title_len: int = 90,
) -> list[dict[str, Any]]:
    """
    Month/day headers (April 14) → weekday; activity + time pairs.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    year = datetime.now().year
    out: list[dict[str, Any]] = []

    current_weekday: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        wd = _weekday_for_month_day_line(line, year)
        if wd is not None:
            current_weekday = wd
            i += 1
            continue

        if current_weekday is None:
            i += 1
            continue

        low = line.lower()
        if "closed for event" in low or low == "closed":
            i += 1
            continue

        if len(line) > max_title_len:
            i += 1
            continue

        if i + 1 >= len(lines):
            i += 1
            continue

        nxt = lines[i + 1].strip()
        if not _HAS_CLOCK.search(nxt) or not _TIME_RANGE_LIKE.search(nxt):
            i += 1
            continue

        if not title_allowed(line):
            i += 2
            continue

        start_t, end_t = parse_time_range_line(nxt)
        if not (start_t and end_t):
            i += 2
            continue

        source_url = stable_recurring_slot_url(
            page_url, frag_prefix, current_weekday, line, start_t, end_t
        )

        out.append(
            {
                "title": line,
                "weekday": current_weekday,
                "start_time": start_t,
                "end_time": end_t,
                "has_time": True,
                "location_label": location_label,
                "type": "recurring",
                "source_url": source_url,
                "description": None,
            }
        )
        i += 2

    return _dedupe_schedule_rows(out)


def parse_pickleball_schedule(html: str, *, page_url: str) -> list[dict[str, Any]]:
    """Pickleball courts schedule (calendar dates + keyword filter)."""
    return _parse_calendar_date_activity_schedule(
        html,
        page_url=page_url,
        title_allowed=_pickleball_title_allowed,
        location_label="Pickleball Courts",
        frag_prefix="pb",
    )


def _community_center_title_allowed(title: str) -> bool:
    t = title.lower()
    keys = (
        "pickleball",
        "glow",
        "open gym",
        "gym",
        "basketball",
        "court",
        "drop in",
    )
    return any(k in t for k in keys)


def parse_community_center_schedule(html: str, *, page_url: str) -> list[dict[str, Any]]:
    """Community Center open gym / GLOW blocks (same date-line pattern as pickleball page)."""
    return _parse_calendar_date_activity_schedule(
        html,
        page_url=page_url,
        title_allowed=_community_center_title_allowed,
        location_label="Community Center",
        frag_prefix="cc",
        max_title_len=90,
    )


def _dedupe_schedule_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repeated week blocks on one page: same location + weekday + title + times → one row."""
    seen: set[tuple[str, str, str, str | None, str | None]] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = (
            str(r.get("location_label") or ""),
            str(r.get("weekday") or ""),
            (r.get("title") or "").strip().lower(),
            r.get("start_time"),
            r.get("end_time"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# Backward-compatible name for callers
def parse_aquatic_center_schedule(html: str, *, page_url: str) -> list[dict[str, Any]]:
    """Deprecated alias — use parse_open_swim_schedule."""
    return parse_open_swim_schedule(html, page_url=page_url)
