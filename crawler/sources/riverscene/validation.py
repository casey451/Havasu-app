from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from typing import Any

# Soft scoring: +1 if any event-ish keyword appears
_EVENT_KEYWORD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bevents?\b", re.I),
    re.compile(r"\bfestival\b", re.I),
    re.compile(r"\bshow\b", re.I),
    re.compile(r"\brace\b", re.I),
    re.compile(r"\bconcert\b", re.I),
    re.compile(r"\blive\b", re.I),
    re.compile(r"\bmusic\b", re.I),
    re.compile(r"\bparty\b", re.I),
)

_TITLE_DISCARD_SUBSTRINGS: tuple[str, ...] = (
    "recap",
    "photos",
    "gallery",
    "highlights",
    "coverage",
)

STRONG_SCORE_THRESHOLD = 4
FINAL_KEEP_SCORE_WITH_START_DATE = 2
FINAL_KEEP_SCORE_WITHOUT_START_DATE = 3
_DESC_LONG_BONUS_CHARS = 150
_DESC_MIN_CHARS_ELIGIBILITY = 80

# Time detection (+2 in scoring; also used for high_confidence)
_TIME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{1,2}:\d{2}\s*(?:[ap]m)\b", re.I),
    re.compile(r"\b\d{1,2}\s*(?:[ap]m)\b", re.I),
    re.compile(r"\b(?:noon|midnight)\b", re.I),
)

_LOCATION_HINTS: tuple[str, ...] = (
    "lake havasu",
    "london bridge",
    "lighthouse",
    "havasu",
    "riverscene",
    "state park",
    "convention",
    "rotary park",
    "grace arts",
    "theatre",
    "theater",
    "marina",
    "resort",
    "venue",
    "boulevard",
    "mcculloch",
    "windsor",
    "aquatic center",
)

# Recognizable date_text / body: month+day, slash dates, relative weekdays
_MONTH_DAY_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}(?:st|nd|rd|th)?\b",
    re.I,
)
_SLASH_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_THIS_WEEKDAY_RE = re.compile(
    r"\bthis\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)


def _coerce_date_val(value: Any) -> date | None:
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


def text_has_recognizable_date(text: str | None) -> bool:
    """
    Loose calendar phrases: April 14, Apr 14, 4/14, 4/14/2026, ISO, this Friday / this Saturday.
    """
    if not text or not str(text).strip():
        return False
    s = str(text).strip()
    if _MONTH_DAY_RE.search(s):
        return True
    if _SLASH_DATE_RE.search(s):
        return True
    if _ISO_DATE_RE.search(s):
        return True
    if _THIS_WEEKDAY_RE.search(s):
        return True
    return False


def has_strict_date_signal(parsed: dict[str, Any]) -> bool:
    """
    Required gate: start_date OR recognizable date in date_text / date_raw / description.
    (end_date alone counts as a parsed calendar signal.)
    """
    if _coerce_date_val(parsed.get("start_date")) is not None:
        return True
    if _coerce_date_val(parsed.get("end_date")) is not None:
        return True
    for key in ("date_text", "date_raw"):
        v = parsed.get(key)
        if isinstance(v, str) and text_has_recognizable_date(v):
            return True
    for key in ("description", "short_description", "title"):
        v = parsed.get(key)
        if isinstance(v, str) and text_has_recognizable_date(v):
            return True
    return False


def _combined_blob(parsed: dict[str, Any]) -> str:
    parts = [
        parsed.get("title") or "",
        parsed.get("description") or "",
        parsed.get("short_description") or "",
        str(parsed.get("date_text") or ""),
        str(parsed.get("date_raw") or ""),
    ]
    return "\n".join(parts)


def has_time_signal(parsed: dict[str, Any]) -> bool:
    blob = _combined_blob(parsed).lower()
    return any(p.search(blob) for p in _TIME_PATTERNS)


def has_location_hint(parsed: dict[str, Any]) -> bool:
    blob = _combined_blob(parsed).lower()
    return any(h in blob for h in _LOCATION_HINTS)


def has_event_keyword(parsed: dict[str, Any]) -> bool:
    blob = _combined_blob(parsed).lower()
    if not blob.strip():
        return False
    return any(p.search(blob) for p in _EVENT_KEYWORD_PATTERNS)


def description_long_bonus(parsed: dict[str, Any]) -> bool:
    desc = parsed.get("description")
    if not isinstance(desc, str):
        return False
    return len(desc.strip()) > _DESC_LONG_BONUS_CHARS


def description_over_min_length(parsed: dict[str, Any], *, min_chars: int = _DESC_MIN_CHARS_ELIGIBILITY) -> bool:
    """Used for eligibility rule: description longer than min_chars (default 80)."""
    desc = parsed.get("description")
    if not isinstance(desc, str):
        return False
    return len(desc.strip()) > min_chars


def title_passes_filter(parsed: dict[str, Any]) -> bool:
    title = (parsed.get("title") or "").lower()
    if not title.strip():
        return False
    return not any(bad in title for bad in _TITLE_DISCARD_SUBSTRINGS)


def compute_event_score(parsed: dict[str, Any]) -> int:
    """
    +2 when calendar/date cues exist (has_strict_date_signal)
    +2 time
    +2 location hint
    +1 event keyword
    +1 description > 150 chars
    """
    score = 0
    if has_strict_date_signal(parsed):
        score += 2
    if has_time_signal(parsed):
        score += 2
    if has_location_hint(parsed):
        score += 2
    if has_event_keyword(parsed):
        score += 1
    if description_long_bonus(parsed):
        score += 1
    return score


def compute_high_confidence(parsed: dict[str, Any]) -> bool:
    """True when both time and location signals are present."""
    return has_time_signal(parsed) and has_location_hint(parsed)


def has_parsed_start_date(parsed: dict[str, Any]) -> bool:
    """True only when the parser produced a structured start_date."""
    return _coerce_date_val(parsed.get("start_date")) is not None


def passes_eligibility_gate(parsed: dict[str, Any]) -> bool:
    """
    Passes if ANY:
    1. has_parsed_start_date AND score >= 2
    2. score >= 4
    3. time_signal AND location_hint AND event_keyword AND description length > 80
    """
    s = compute_event_score(parsed)
    if has_parsed_start_date(parsed) and s >= 2:
        return True
    if s >= STRONG_SCORE_THRESHOLD:
        return True
    if (
        has_time_signal(parsed)
        and has_location_hint(parsed)
        and has_event_keyword(parsed)
        and description_over_min_length(parsed)
    ):
        return True
    return False


def passes_final_keep_threshold(parsed: dict[str, Any], score: int) -> bool:
    """
    After title + eligibility: if parsed start_date, keep when score >= 2; else keep when score >= 3.
    """
    if has_parsed_start_date(parsed):
        return score >= FINAL_KEEP_SCORE_WITH_START_DATE
    return score >= FINAL_KEEP_SCORE_WITHOUT_START_DATE


def should_keep_riverscene_event(parsed: dict[str, Any]) -> bool:
    """Title filter + eligibility + final score threshold."""
    if not title_passes_filter(parsed):
        return False
    if not passes_eligibility_gate(parsed):
        return False
    s = compute_event_score(parsed)
    return passes_final_keep_threshold(parsed, s)


def summarize_score_distribution(scores: Counter[int]) -> str:
    parts = [f"{k}:{scores[k]}" for k in sorted(scores.keys())]
    return "{" + ", ".join(parts) + "}" if parts else "{}"
