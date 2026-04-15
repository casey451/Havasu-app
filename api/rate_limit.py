from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

WINDOW_SEC = 60.0
PATH_LIMITS_PER_MINUTE: Final[dict[str, int]] = {
    "/submit": 10,
    "/track/view": 60,
    "/track/click": 60,
}


def rate_limit_disabled() -> bool:
    return os.environ.get("HAVASU_RATE_LIMIT_DISABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory sliding window for selected endpoints only.
    Not shared across multiple workers or restarts — replace with Redis (etc.) when scaling.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, list[float]] = defaultdict(list)  # key = "{ip}|{path}"

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        if rate_limit_disabled():
            return await call_next(request)
        if request.method != "POST":
            return await call_next(request)
        path = request.url.path
        limit = PATH_LIMITS_PER_MINUTE.get(path)
        if limit is None:
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()
        cutoff = now - WINDOW_SEC
        key = f"{ip}|{path}"
        arr = self._hits[key]
        arr[:] = [t for t in arr if t > cutoff]
        if len(arr) >= limit:
            logger.warning("rate_limit exceeded ip=%s path=%s", ip, path)
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited"},
            )
        arr.append(now)
        return await call_next(request)
