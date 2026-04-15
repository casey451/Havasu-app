from __future__ import annotations

from core.http import build_client
from core.storage import sha256_text
from db.database import upsert_raw_page


def fetch_and_store_page(url: str, source: str = "golakehavasu") -> int:
    with build_client() as client:
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
