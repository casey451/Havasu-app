from __future__ import annotations

from typing import Any

from core.sources import SOURCE_RIVERSCENE


def should_store(payload: dict[str, Any]) -> bool:
    """
    Global gate: no empty titles, events must have start_date,
    recurring must have weekday + time range.
    """
    t = payload.get("title")
    if not isinstance(t, str) or len(t.strip()) < 3:
        return False

    typ = payload.get("type")
    if typ == "event":
        sd = payload.get("start_date")
        if sd is None:
            return False
        if isinstance(sd, str) and not sd.strip():
            return False
        src = (payload.get("source") or "").strip()
        if src == SOURCE_RIVERSCENE:
            for key in ("start_time", "end_time"):
                v = payload.get(key)
                if v is None or not isinstance(v, str) or not v.strip():
                    return False
        return True

    if typ == "recurring":
        for key in ("weekday", "start_time", "end_time"):
            v = payload.get(key)
            if v is None or not isinstance(v, str) or not v.strip():
                return False
        return True

    if typ == "program":
        return True

    return False
