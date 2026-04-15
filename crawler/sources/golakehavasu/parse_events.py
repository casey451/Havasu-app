from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

_MAX_DESCRIPTION_LEN = 280
_SHORT_DESC_MIN = 120
_SHORT_DESC_MAX = 180

def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _clean_description(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if len(text) > _MAX_DESCRIPTION_LEN:
        text = text[: _MAX_DESCRIPTION_LEN].rstrip() + "…"
    return text


def _build_short_description(description: str | None, date_text: str | None) -> str | None:
    """First 120–180 chars, prefer sentence boundaries; never duplicate the full description."""
    if not description:
        return None
    work = description.strip()
    if date_text:
        dt = date_text.strip()
        if dt and work.lower().startswith(dt.lower()):
            work = work[len(dt) :].lstrip(" ,.-–\n")
    work = _clean_text(work)
    if not work:
        work = _clean_text(description)

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", work) if s.strip()]
    if not sentences:
        return None

    chunk = sentences[0]
    idx = 1
    while len(chunk) < _SHORT_DESC_MIN and idx < len(sentences):
        nxt = f"{chunk} {sentences[idx]}".strip()
        if len(nxt) > _SHORT_DESC_MAX:
            break
        chunk = nxt
        idx += 1

    if len(chunk) > _SHORT_DESC_MAX:
        trimmed = chunk[: _SHORT_DESC_MAX]
        cut = trimmed.rsplit(" ", 1)[0].strip()
        chunk = (cut if len(cut) >= 40 else trimmed.rstrip()) + "…"

    full_norm = _clean_text(description)
    chunk_norm = _clean_text(chunk)
    if chunk_norm and full_norm and chunk_norm == full_norm:
        excerpt = work[:145].rsplit(" ", 1)[0].strip()
        chunk = excerpt + ("…" if len(excerpt) < len(work) else "")
    elif full_norm and chunk_norm == full_norm[: len(chunk_norm)] and len(full_norm) - len(chunk_norm) <= 3:
        excerpt = work[:130].rsplit(" ", 1)[0].strip()
        chunk = excerpt + ("…" if len(excerpt) < len(work) else "")

    return _clean_text(chunk) or None


def _strip_redundant_opening_date(description: str | None, date_raw: str | None) -> str | None:
    if not description:
        return None
    d = description.strip()
    if date_raw:
        dr = date_raw.strip()
        if dr and d.lower().startswith(dr.lower()):
            d = d[len(dr) :].lstrip(" ,.-–\n")
    thru_re = re.compile(
        r"^[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:through|thru)\s+"
        r"[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s*\d{4}\s*",
        flags=re.I,
    )
    for _ in range(2):
        m_thru = thru_re.match(d)
        if not m_thru:
            break
        d = d[m_thru.end() :].lstrip()
    return _clean_description(d)


def _parse_single_date(text: str) -> date | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def extract_date_range(text: str | None) -> tuple[date | None, date | None]:
    """
    Pull a start/end calendar date from free text.
    Returns (None, None) when no range or single date is recognized.
    """
    blob = _clean_text(text)
    if not blob:
        return None, None

    # January 31st thru February 1st, 2026
    thru = re.search(
        r"(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(?:through|thru|to)\s+"
        r"(?P<m2>[A-Za-z]+)\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?,\s*"
        r"(?P<y>\d{4})",
        blob,
        flags=re.I,
    )
    if thru:
        y = thru.group("y")
        left = _parse_single_date(f"{thru.group('m1')} {thru.group('d1')}, {y}")
        right = _parse_single_date(f"{thru.group('m2')} {thru.group('d2')}, {y}")
        if left and right:
            return left, right

    # Same month range: October 15-19, 2025
    same_month = re.search(
        r"(?P<m>[A-Za-z]+)\s+(?P<d1>\d{1,2})\s*[-–]\s*(?P<d2>\d{1,2}),\s*(?P<y>\d{4})",
        blob,
        flags=re.I,
    )
    if same_month:
        m, d1, d2, y = (
            same_month.group("m"),
            same_month.group("d1"),
            same_month.group("d2"),
            same_month.group("y"),
        )
        left = _parse_single_date(f"{m} {d1}, {y}")
        right = _parse_single_date(f"{m} {d2}, {y}")
        if left and right:
            return left, right

    # Cross-month numeric range without year between: Jan 28 - Feb 1, 2026
    cross = re.search(
        r"(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*"
        r"(?P<m2>[A-Za-z]+)\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?,\s*(?P<y>\d{4})",
        blob,
        flags=re.I,
    )
    if cross:
        y = cross.group("y")
        left = _parse_single_date(f"{cross.group('m1')} {cross.group('d1')}, {y}")
        right = _parse_single_date(f"{cross.group('m2')} {cross.group('d2')}, {y}")
        if left and right:
            return left, right

    # Single explicit short phrase: "October 3, 2026"
    single_mdy = re.search(
        r"\b([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s*\d{4})\b",
        blob,
    )
    if single_mdy:
        single = _parse_single_date(single_mdy.group(1))
        if single:
            return single, single

    # All "Month DD, YYYY" occurrences → event span (e.g. multi-day hours lines)
    all_explicit: list[date] = []
    for m in re.finditer(
        r"\b([A-Za-z]{3,12}\s+\d{1,2}(?:st|nd|rd|th)?,\s*\d{4})\b",
        blob,
        flags=re.I,
    ):
        d = _parse_single_date(m.group(1))
        if d:
            all_explicit.append(d)
    if all_explicit:
        return min(all_explicit), max(all_explicit)

    # "Friday, April 17, 2026" (weekday + month + day + year)
    wd_mdy = re.search(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*"
        r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})\b",
        blob,
        flags=re.I,
    )
    if wd_mdy:
        single = _parse_single_date(
            f"{wd_mdy.group(1)} {wd_mdy.group(2)}, {wd_mdy.group(3)}"
        )
        if single:
            return single, single

    # Slash or ISO single dates
    slash = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", blob)
    if slash:
        d = _parse_single_date(slash.group(1))
        if d:
            return d, d
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", blob)
    if iso:
        d = _parse_single_date(iso.group(1))
        if d:
            return d, d

    # "this Saturday" / "this Friday" (relative)
    if re.search(
        r"\bthis\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        blob,
        flags=re.I,
    ):
        m_rel = re.search(
            r"\b(this\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
            blob,
            flags=re.I,
        )
        if m_rel:
            try:
                dt = date_parser.parse(m_rel.group(1), fuzzy=True, default=datetime.now())
                d = dt.date()
                return d, d
            except (ValueError, OverflowError, TypeError):
                pass

    # Month + day without year (e.g. show hours); infer year from first 20xx in text or today
    inferred = _extract_dates_with_inferred_year(blob)
    if inferred:
        return min(inferred), max(inferred)

    return None, None


_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
)


def _infer_year_for_blob(blob: str) -> int:
    from datetime import date

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", blob)]
    if years:
        return years[0]
    return date.today().year


def _extract_dates_with_inferred_year(blob: str) -> list[date]:
    """Parse month+day tokens when year is missing but appears elsewhere in blob (or use current year)."""
    y_default = _infer_year_for_blob(blob)
    out: list[date] = []
    # Weekday + Month + Day (no year on that fragment)
    for m in re.finditer(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*"
        r"([A-Za-z]{3,12})\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\s*,\s*\d{4})",
        blob,
        flags=re.I,
    ):
        mon, day = m.group(1), m.group(2)
        if mon.lower() not in _MONTH_NAMES:
            continue
        d = _parse_single_date(f"{mon} {day}, {y_default}")
        if d:
            out.append(d)
    # Month + Day without weekday (avoid matching twice if already got weekday lines)
    for m in re.finditer(
        r"(?<![A-Za-z])"  # not mid-word
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\s*,\s*\d{4})",
        blob,
        flags=re.I,
    ):
        mon, day = m.group(1), m.group(2)
        d = _parse_single_date(f"{mon} {day}, {y_default}")
        if d:
            out.append(d)
    # Dedupe by date
    seen: set[date] = set()
    uniq: list[date] = []
    for d in sorted(out):
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def _ampm_to_24h(hour: int, minute: int, ampm: str) -> str:
    ampm_u = ampm.strip().upper()
    if ampm_u == "AM":
        h = 0 if hour == 12 else hour
    elif ampm_u == "PM":
        h = 12 if hour == 12 else hour + 12
    else:
        h = hour
    return f"{h:02d}:{minute:02d}"


def extract_time_range(text: str | None) -> tuple[str | None, str | None]:
    """
    Extract a clock range from free text. Returns 24-hour "HH:MM" strings or (None, None).
    """
    blob = _clean_text(text)
    if not blob:
        return None, None

    # 12:00 PM – 3:00 PM (en/em dash variants)
    clock = re.search(
        r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*(?:[-–—]|to)\s*(\d{1,2}):(\d{2})\s*(AM|PM)",
        blob,
        flags=re.I,
    )
    if clock:
        h1, m1, ap1, h2, m2, ap2 = (
            int(clock.group(1)),
            int(clock.group(2)),
            clock.group(3),
            int(clock.group(4)),
            int(clock.group(5)),
            clock.group(6),
        )
        return _ampm_to_24h(h1, m1, ap1), _ampm_to_24h(h2, m2, ap2)

    # 5-8pm or 5:30pm-9pm (compact)
    compact = re.search(
        r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(?:[-–—]|to)\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)",
        blob,
        flags=re.I,
    )
    if compact:
        h1 = int(compact.group(1))
        m1 = int(compact.group(2) or 0)
        ap1 = compact.group(3)
        h2 = int(compact.group(4))
        m2 = int(compact.group(5) or 0)
        ap2 = compact.group(6)
        return _ampm_to_24h(h1, m1, ap1), _ampm_to_24h(h2, m2, ap2)

    # 5-9pm or 5 - 9 pm (shared meridiem)
    shared = re.search(
        r"(\d{1,2})(?::(\d{2}))?\s*(?:[-–—]|to)\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\b",
        blob,
        flags=re.I,
    )
    if shared:
        h1 = int(shared.group(1))
        m1 = int(shared.group(2) or 0)
        h2 = int(shared.group(3))
        m2 = int(shared.group(4) or 0)
        ap = shared.group(5)
        return _ampm_to_24h(h1, m1, ap), _ampm_to_24h(h2, m2, ap)

    # Noon to 3pm / 3pm to noon
    noon_range = re.search(
        r"\bnoon\b\s*(?:[-–—]|to)\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\b",
        blob,
        flags=re.I,
    )
    if noon_range:
        h2 = int(noon_range.group(1))
        m2 = int(noon_range.group(2) or 0)
        ap2 = noon_range.group(3)
        return "12:00", _ampm_to_24h(h2, m2, ap2)

    noon_range_rev = re.search(
        r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*(?:[-–—]|to)\s*\bnoon\b",
        blob,
        flags=re.I,
    )
    if noon_range_rev:
        h1 = int(noon_range_rev.group(1))
        m1 = int(noon_range_rev.group(2) or 0)
        ap1 = noon_range_rev.group(3)
        return _ampm_to_24h(h1, m1, ap1), "12:00"

    # Single Noon mention
    if re.search(r"\bnoon\b", blob, flags=re.I):
        return "12:00", None

    return None, None


def extract_address(text: str | None) -> tuple[str | None, str | None]:
    """
    Split a venue label from a trailing US-style street + city + state + ZIP segment.
    """
    blob = _clean_text(text)
    if not blob:
        return None, None

    # e.g. "Resort1477 Queens Bay" -> "Resort, 1477 Queens Bay"
    blob = re.sub(r"([A-Za-z])(\d{3,5}\s+[A-Za-z0-9])", r"\1, \2", blob)
    # e.g. "Resort 1477 Queens Bay" -> "Resort, 1477 Queens Bay"
    blob = re.sub(r"([A-Za-z])\s+(\d{3,5}\s+[A-Za-z0-9])", r"\1, \2", blob)

    _state = r"(?:Arizona|California|Nevada|Utah|Colorado|[A-Z]{2})"

    # "... , 171 London Bridge Rd Lake Havasu City, AZ 86403"
    match = re.search(
        rf",\s*((?:\d{{1,5}})\s+.+),\s*([^,]+),\s*({_state})\s+(\d{{5}}(?:-\d{{4}})?)\s*$",
        blob,
        flags=re.S,
    )
    if match:
        address = f"{match.group(1).strip()}, {match.group(2).strip()}, {match.group(3)} {match.group(4)}"
        venue = blob[: match.start()].strip()
        return (venue or None, address or None)

    # "... , 171 London Bridge Rd ..., AZ 86403" (no extra comma before state)
    match_short = re.search(
        rf",\s*((?:\d{{1,5}})\s+.+),\s*({_state})\s+(\d{{5}}(?:-\d{{4}})?)\s*$",
        blob,
        flags=re.S,
    )
    if match_short:
        address = f"{match_short.group(1).strip()}, {match_short.group(2)} {match_short.group(3)}"
        venue = blob[: match_short.start()].strip()
        return (venue or None, address or None)

    # Single comma before "State ZIP" (e.g. "... Lake Havasu City, Arizona 86403")
    tail = re.search(rf",\s*({_state})\s+(\d{{5}}(?:-\d{{4}})?)\s*$", blob)
    if tail:
        venue = blob[: tail.start()].strip()
        city_tail = re.search(r"\b([A-Za-z][A-Za-z\s]+City)\s*$", venue)
        if city_tail:
            venue = venue[: city_tail.start()].strip().rstrip(",")
            address = f"{city_tail.group(1).strip()}, {tail.group(1)} {tail.group(2)}"
        else:
            address = f"{tail.group(1)} {tail.group(2)}"
        return (venue or None, address or None)

    # Fallback: line looks like a full street address without a leading comma split
    street_only = re.fullmatch(
        r"(\d{1,5}\s+.+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)",
        blob,
        flags=re.S,
    )
    if street_only:
        return None, blob

    return blob, None


def _extract_address_fragment(text: str | None) -> str | None:
    blob = _clean_text(text)
    if not blob:
        return None
    pattern = re.search(
        r"((?:\d{1,5}\s+[A-Za-z0-9 .#'-]+)\s+Lake Havasu City,\s*(?:AZ|Arizona)\s+\d{5}(?:-\d{4})?)",
        blob,
        flags=re.I,
    )
    if pattern:
        return _clean_text(pattern.group(1))
    city_only = re.search(r"(Lake Havasu City,\s*(?:AZ|Arizona)\s+\d{5}(?:-\d{4})?)", blob, flags=re.I)
    if city_only:
        return _clean_text(city_only.group(1))
    return None


def _cleanup_venue_name(venue_name: str | None, address: str | None) -> str | None:
    venue = _clean_text(venue_name)
    if not venue:
        return None
    if address:
        venue = venue.replace(address, "").strip(" ,-")
    venue = re.sub(r"\bLake Havasu City,\s*(?:AZ|Arizona)\s+\d{5}(?:-\d{4})?\b", "", venue, flags=re.I)
    venue = re.sub(r"\b\d{1,5}\s+[A-Za-z0-9 .#'-]+\b$", "", venue).strip(" ,-")
    return _finalize_venue_name(venue)


def _finalize_venue_name(venue: str | None) -> str | None:
    v = _clean_text(venue)
    if not v:
        return None
    v = v.strip(" ,")
    v = re.sub(r",\s*$", "", v)
    v = re.sub(r"\s*,\s*,+", ", ", v)
    v = re.sub(r"\b\d{5}(?:-\d{4})?\s*$", "", v).strip(" ,-")
    v = re.sub(r",\s*(?:AZ|Arizona)\s*$", "", v, flags=re.I).strip(" ,-")
    return v or None


def _extract_section_text(soup: BeautifulSoup, heading: str) -> str | None:
    node = soup.find(
        lambda tag: tag.name in {"h2", "h3", "h4"} and _clean_text(tag.get_text()) == heading
    )
    if node is None:
        return None

    values: list[str] = []
    sibling = node.find_next_sibling()
    while sibling is not None and sibling.name not in {"h2", "h3", "h4"}:
        text = _clean_text(sibling.get_text(" ", strip=True))
        if text:
            values.append(text)
        sibling = sibling.find_next_sibling()
    joined = " ".join(values).strip()
    return joined or None


def _extract_date_line(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1 is not None:
        next_heading = h1.find_next(lambda tag: tag.name in {"h2", "h3"})
        if next_heading is not None:
            raw = _clean_text(next_heading.get_text(" ", strip=True))
            return raw or None
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        raw = _clean_text(str(meta["content"]))
        return raw or None
    return None


def _extract_description(soup: BeautifulSoup) -> str | None:
    h1 = soup.find("h1")
    if h1 is None:
        return None
    texts: list[str] = []
    pointer = h1.find_next_sibling()
    while pointer is not None and pointer.name not in {"h2", "h3"}:
        text = _clean_text(pointer.get_text(" ", strip=True))
        if text:
            texts.append(text)
        pointer = pointer.find_next_sibling()
    joined = "\n\n".join(texts).strip()
    return _clean_description(joined)


def _merge_date_hints(
    headline: str | None,
    description: str | None,
    schedule: str | None,
    admission: str | None,
) -> tuple[date | None, date | None]:
    for chunk in (headline, description, schedule, admission):
        start, end = extract_date_range(chunk)
        if start or end:
            return start, end
    return None, None


def _merge_time_hints(*chunks: str | None) -> tuple[str | None, str | None]:
    blob = _clean_text(" ".join(c for c in chunks if c))
    start, end = extract_time_range(blob)
    if start or end:
        return start, end
    return None, None


def parse_event_page(html: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.find("h1")
    title = _clean_text(title_el.get_text(" ", strip=True)) if title_el else None
    if title == "":
        title = None

    date_raw = _extract_date_line(soup)
    location_raw = _extract_section_text(soup, "Location")
    schedule_raw = _extract_section_text(soup, "Schedule")
    admission_raw = _extract_section_text(soup, "Admission")
    description = _extract_description(soup)
    description = _strip_redundant_opening_date(description, date_raw)

    venue_guess, address_guess = extract_address(location_raw)
    venue_name = venue_guess
    address = address_guess
    if address is None:
        address = _extract_address_fragment(location_raw) or _extract_address_fragment(description)
    venue_name = _cleanup_venue_name(venue_name, address)

    text_for_dates = " ".join(
        filter(
            None,
            (
                date_raw,
                description,
                schedule_raw,
                admission_raw,
            ),
        )
    )
    start_d, end_d = _merge_date_hints(date_raw, description, schedule_raw, admission_raw)
    if not start_d and not end_d:
        start_d, end_d = extract_date_range(text_for_dates)

    date_text = _clean_text(date_raw) or None

    time_blob = " ".join(filter(None, (description, schedule_raw, admission_raw, date_raw)))
    start_t, end_t = _merge_time_hints(time_blob)
    short_description = _build_short_description(description, date_text)

    if not (start_d or end_d):
        logger.info("Date not found for %s", source_url)
    if not (start_t or end_t):
        logger.info("Time not found for %s", source_url)
    if not address:
        logger.info("Address not found for %s", source_url)

    return {
        "title": title,
        "date_raw": date_raw,
        "date_text": date_text,
        "start_date": start_d,
        "end_date": end_d,
        "start_time": start_t,
        "end_time": end_t,
        "venue_name": venue_name,
        "address": address,
        "description": description,
        "short_description": short_description,
        "source_url": source_url,
    }
