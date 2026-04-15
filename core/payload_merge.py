from __future__ import annotations

import difflib
import json
import sqlite3
from typing import Any

from core.item_identity import normalize_event_date_key, normalize_event_title_key


def _s(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


def _longest_non_empty(*parts: str) -> str:
    nonempty = [p for p in parts if p]
    if not nonempty:
        return ""
    return max(nonempty, key=len)


def _collect_source_urls(payload: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    raw_list = payload.get("source_urls")
    if isinstance(raw_list, list):
        for u in raw_list:
            if isinstance(u, str) and u.strip() and u.strip() not in seen:
                seen.add(u.strip())
                out.append(u.strip())
    su = payload.get("source_url")
    if isinstance(su, str) and su.strip() and su.strip() not in seen:
        out.append(su.strip())
    return out


def merge_event_payloads(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """
    Combine two event payloads. Keeps existing title when non-empty; fills gaps;
    prefers richer description and location; accumulates source_urls.
    """
    out = dict(existing)
    if not _s(existing.get("title")):
        out["title"] = incoming.get("title", "")

    for k in ("start_time", "end_time"):
        old_v, new_v = _s(existing.get(k)), _s(incoming.get(k))
        out[k] = old_v if old_v else new_v

    out["start_date"] = _pick_start_date(existing, incoming)
    out["end_date"] = _pick_end_date(existing, incoming, out["start_date"])

    ol, il = _s(existing.get("location_label")), _s(incoming.get("location_label"))
    out["location_label"] = ol if ol else il

    for k in ("venue_name", "address"):
        ov, nv = existing.get(k), incoming.get(k)
        o_str, n_str = _s(ov), _s(nv)
        out[k] = ov if o_str else (nv if n_str else ov)

    e_desc, e_short = _s(existing.get("description")), _s(existing.get("short_description"))
    i_desc, i_short = _s(incoming.get("description")), _s(incoming.get("short_description"))
    longest = _longest_non_empty(e_desc, e_short, i_desc, i_short)
    out["description"] = longest if longest else existing.get("description")
    short_best = _longest_non_empty(e_short, i_short)
    out["short_description"] = short_best if short_best else incoming.get("short_description")

    urls: list[str] = []
    seen: set[str] = set()
    for u in _collect_source_urls(existing) + _collect_source_urls(incoming):
        if u not in seen:
            seen.add(u)
            urls.append(u)
    out["source_urls"] = urls
    if _s(existing.get("source_url")):
        out["source_url"] = existing.get("source_url")
    else:
        out["source_url"] = incoming.get("source_url")

    return out


def _pick_start_date(existing: dict[str, Any], incoming: dict[str, Any]) -> str:
    o, n = _s(existing.get("start_date")), _s(incoming.get("start_date"))
    if o == n:
        return o
    if not n:
        return o
    if not o:
        return n

    def venue_score(d: dict[str, Any]) -> bool:
        return bool(_s(d.get("venue_name")) or _s(d.get("address")))

    if venue_score(incoming) and not venue_score(existing):
        return n
    if venue_score(existing) and not venue_score(incoming):
        return o
    if (incoming.get("source") or "").strip() == "golakehavasu":
        return n
    if (existing.get("source") or "").strip() == "golakehavasu":
        return o
    return o


def _pick_end_date(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    chosen_start: str,
) -> str:
    o, n = _s(existing.get("end_date")), _s(incoming.get("end_date"))
    o_sd, n_sd = _s(existing.get("start_date")), _s(incoming.get("start_date"))
    if o_sd == chosen_start and o:
        return o
    if n_sd == chosen_start and n:
        return n
    return o if o else n


def title_similarity_ratio(a: str | None, b: str | None) -> float:
    ta = normalize_event_title_key(a)
    tb = normalize_event_title_key(b)
    if not ta or not tb:
        return 0.0
    return difflib.SequenceMatcher(None, ta, tb).ratio()


def find_cross_source_event_candidate_id(
    conn: sqlite3.Connection,
    incoming: dict[str, Any],
    *,
    exclude_id: int | None = None,
    min_ratio: float = 0.86,
) -> int | None:
    """
    Find an existing event row (different source) that likely describes the same occurrence,
    using time match + title similarity, or date match + title similarity.
    """
    if (incoming.get("type") or "").strip() != "event":
        return None
    source = (incoming.get("source") or "").strip()
    ist, iet = _s(incoming.get("start_time")), _s(incoming.get("end_time"))
    rows: list[sqlite3.Row]
    if ist and iet:
        rows = conn.execute(
            """
            SELECT id, payload_json FROM items
            WHERE type = 'event' AND source != ?
              AND lower(trim(coalesce(json_extract(payload_json, '$.start_time'), ''))) = ?
              AND lower(trim(coalesce(json_extract(payload_json, '$.end_time'), ''))) = ?
            """,
            (source, ist.lower(), iet.lower()),
        ).fetchall()
    else:
        isd = normalize_event_date_key(incoming.get("start_date"))
        if not isd:
            return None
        rows = conn.execute(
            """
            SELECT id, payload_json FROM items
            WHERE type = 'event' AND source != ?
              AND substr(trim(coalesce(json_extract(payload_json, '$.start_date'), '')), 1, 10) = ?
            """,
            (source, isd),
        ).fetchall()

    ititle = incoming.get("title")
    best_id: int | None = None
    best_ratio = 0.0
    for row in rows:
        rid = int(row["id"])
        if exclude_id is not None and rid == exclude_id:
            continue
        p = json.loads(row["payload_json"])
        r = title_similarity_ratio(ititle, p.get("title"))
        if r >= min_ratio and r > best_ratio:
            best_ratio = r
            best_id = rid
    return best_id
