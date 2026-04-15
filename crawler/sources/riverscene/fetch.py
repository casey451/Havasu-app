from __future__ import annotations

import json
from typing import Any

from core.http import build_client
from core.storage import sha256_text
from db.database import upsert_raw_page


def fetch_and_store_page(url: str, source: str = "riverscene") -> int:
    with build_client(timeout_seconds=60.0) as client:
        response = client.get(url)
    response.raise_for_status()
    html = response.text
    return upsert_raw_page(
        url=str(response.url),
        source=source,
        status_code=response.status_code,
        html=html,
        content_sha256=sha256_text(html),
    )


def store_api_post_payload(post: dict[str, Any], source: str = "riverscene") -> int:
    """
    Persist the WordPress post JSON as the raw blob (stored in raw_pages.html column).
    """
    url = (post.get("link") or "").strip()
    if not url:
        raise ValueError("WordPress post missing link")

    payload = json.dumps(post, ensure_ascii=True)
    return upsert_raw_page(
        url=url,
        source=source,
        status_code=200,
        html=payload,
        content_sha256=sha256_text(payload),
    )
