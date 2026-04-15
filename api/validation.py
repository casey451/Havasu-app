from __future__ import annotations

import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str:
    if text is None:
        return ""
    s = _TAG_RE.sub("", str(text))
    return unescape(s).strip()


def clamp_title(s: str, max_len: int = 120) -> str:
    t = strip_html(s)
    return t[:max_len]


def clamp_description(s: str | None, max_len: int = 2000) -> str | None:
    if s is None:
        return None
    t = strip_html(s)
    if not t:
        return None
    return t[:max_len]
