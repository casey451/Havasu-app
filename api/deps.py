from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.security import decode_token
from db.accounts import get_business_by_id

security = HTTPBearer(auto_error=True)


class CurrentUser:
    __slots__ = ("id", "email", "role", "status", "name")

    def __init__(
        self,
        *,
        id: int,
        email: str,
        role: str,
        status: str,
        name: str,
    ) -> None:
        self.id = id
        self.email = email
        self.role = role
        self.status = status
        self.name = name


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> CurrentUser:
    try:
        payload = decode_token(creds.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    try:
        uid = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token subject")
    row = get_business_by_id(uid)
    if row is None:
        raise HTTPException(status_code=401, detail="User not found")
    return CurrentUser(
        id=int(row["id"]),
        email=str(row["email"]),
        role=str(row["role"]),
        status=str(row["status"]),
        name=str(row["name"]),
    )


async def get_current_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


async def get_current_approved_business(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if user.role != "business":
        raise HTTPException(status_code=403, detail="Business account required")
    if user.status != "approved":
        raise HTTPException(status_code=403, detail="Business not approved yet")
    return user
