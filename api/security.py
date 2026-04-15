from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def _jwt_secret() -> str:
    s = os.environ.get("HAVASU_JWT_SECRET", "").strip()
    if s:
        return s
    env = os.environ.get("HAVASU_ENV", "").strip().lower()
    if env in ("production", "prod"):
        raise RuntimeError(
            "HAVASU_JWT_SECRET must be set when HAVASU_ENV is production (or prod)."
        )
    logger.warning(
        "HAVASU_JWT_SECRET not set; using insecure dev default. Set env for production."
    )
    return "dev-only-insecure-jwt-secret-change-me"


def create_access_token(
    *,
    user_id: int,
    role: str,
    email: str,
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, str | int]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
    except JWTError as e:
        raise ValueError("invalid token") from e
