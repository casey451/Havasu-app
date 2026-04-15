from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_REGISTER_HREF_RE = re.compile(r"register\.lhcaz\.gov|/register", re.I)

# Titles we never store as programs (nav / boilerplate).
_EXCLUDE_TITLE_SUBSTR = (
    "click here",
    "register online",
    "questions or comments",
    "season details",
    "age groups",
    "format:",
    "dates:",
    "prior to registration",
    "volunteer",
    "@",
    "http",
    "link to registration",
    "brook dubay",
    "check back soon",
)


def _find_registration_url(soup: BeautifulSoup, page_url: str) -> str | None:
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if _REGISTER_HREF_RE.search(href) or "register" in a.get_text(" ", strip=True).lower():
            return urljoin(page_url, href).split("#")[0].rstrip("/")
    return None


def _title_ok(title: str) -> bool:
    t = title.strip()
    if len(t) < 8 or len(t) > 120:
        return False
    low = t.lower()
    if any(x in low for x in _EXCLUDE_TITLE_SUBSTR):
        return False
    if t.isdigit():
        return False
    return True


def _program_source_url(page_url: str, slug: str) -> str:
    base = page_url.split("#")[0].rstrip("/")
    return f"{base}#program-{slug}"


def parse_youth_athletics_programs(html: str, *, page_url: str) -> list[dict[str, Any]]:
    """
    High-confidence program rows from headings (leagues). type=program.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    reg = _find_registration_url(soup, page_url)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for tag in soup.find_all(["strong", "h2", "h3", "h4"]):
        title = tag.get_text(" ", strip=True)
        if not _title_ok(title):
            continue
        # Prefer league / sport phrasing
        low = title.lower()
        if not any(
            k in low
            for k in (
                "league",
                "football",
                "basketball",
                "flag",
                "jr.",
                "jrs",
                "suns",
                "nfl",
            )
        ):
            continue
        key = low
        if key in seen:
            continue
        seen.add(key)

        desc_bits: list[str] = []
        for sib in list(tag.next_siblings)[:4]:
            if getattr(sib, "get_text", None):
                tx = sib.get_text(" ", strip=True)
                if tx and len(tx) > 20:
                    desc_bits.append(tx[:400])
                    break
        description = " ".join(desc_bits)[:500] or None

        slug = re.sub(r"[^a-zA-Z0-9]+", "-", low).strip("-")[:56]
        out.append(
            {
                "type": "program",
                "title": title,
                "weekday": None,
                "start_time": None,
                "end_time": None,
                "has_time": False,
                "location_label": "Youth Athletics",
                "description": description,
                "external_url": reg,
                "source_url": _program_source_url(page_url, slug or "row"),
            }
        )

    return out


def parse_programs_activities_page(html: str, *, page_url: str) -> list[dict[str, Any]]:
    """
    Section-level program buckets (adult/youth/tots). type=program.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    reg = _find_registration_url(soup, page_url)
    # Major section headings (ALL CAPS blocks on the live page).
    targets = (
        "TINY TOTS PROGRAMS",
        "YOUTH PROGRAMS",
        "ADULT PROGRAMS",
        "ALL AGES PROGRAMS",
    )
    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    for tag in soup.find_all(["h2", "h3", "h4", "strong"]):
        title = tag.get_text(" ", strip=True)
        if title.upper() not in targets and title not in targets:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        desc = None
        for sib in list(tag.next_siblings)[:6]:
            if getattr(sib, "name", None) == "p":
                desc = sib.get_text(" ", strip=True)[:500]
                break
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:56]
        out.append(
            {
                "type": "program",
                "title": title,
                "weekday": None,
                "start_time": None,
                "end_time": None,
                "has_time": False,
                "location_label": "Programs & Activities",
                "description": desc,
                "external_url": reg,
                "source_url": _program_source_url(page_url, slug or "section"),
            }
        )

    return out
