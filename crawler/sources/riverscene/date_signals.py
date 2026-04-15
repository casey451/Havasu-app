"""Heuristics for RiverScene event date trust (avoid wrong dates on homepage)."""
from __future__ import annotations

import logging
import re
from datetime import date

logger = logging.getLogger(__name__)

# Title phrases that imply a specific season; if stored calendar date is far off, drop it.
_NYE = re.compile(
    r"\b(new\s+year|noon\s+year|year[\u2019']s\s+eve|nye)\b",
    re.I,
)
_XMAS = re.compile(r"\b(christmas|x-?mas|holiday\s+light)\b", re.I)
_THANKS = re.compile(r"\bthanksgiving\b", re.I)
_EASTER = re.compile(r"\beaster\b", re.I)
_HALLOWEEN = re.compile(r"\bhalloween\b", re.I)
_VAL = re.compile(r"\bvalentine\b", re.I)
_JULY4 = re.compile(r"\b(july\s*4|fourth\s+of\s+july|4th\s+of\s+july)\b", re.I)
_STPAT = re.compile(r"\bst\.?\s*patrick|st\s+paddy\b", re.I)


def title_implies_seasonal_mismatch(title: str | None, start: date | None) -> bool:
    """
    Return True if start_date is likely wrong given obvious seasonal wording in title.
    When True, caller should clear start/end/date_text rather than show a bogus day.
    """
    if not title or not start:
        return False
    t = title.lower()
    m, d = start.month, start.day

    if _NYE.search(t):
        # NYE / noon-year: expect late Dec or very early Jan
        if m == 12 and d >= 28:
            return False
        if m == 1 and d <= 5:
            return False
        logger.debug(
            "riverscene_date: title/season mismatch (NYE-ish title, date %s)",
            start.isoformat(),
        )
        return True

    if _XMAS.search(t):
        if m == 12 and 15 <= d <= 26:
            return False
        logger.debug(
            "riverscene_date: title/season mismatch (Christmas-ish title, date %s)",
            start.isoformat(),
        )
        return True

    if _THANKS.search(t):
        if m == 11 and 20 <= d <= 30:
            return False
        return True

    if _EASTER.search(t):
        if m in (3, 4):
            return False
        return True

    if _HALLOWEEN.search(t):
        if m == 10 and 25 <= d <= 31:
            return False
        return True

    if _VAL.search(t):
        if m == 2 and 10 <= d <= 15:
            return False
        return True

    if _JULY4.search(t):
        if m == 7 and 1 <= d <= 7:
            return False
        return True

    if _STPAT.search(t):
        if m == 3 and 15 <= d <= 19:
            return False
        return True

    return False
