from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from api.deps import CurrentUser, get_current_user
from api.security import create_access_token
from core.passwords import hash_password, verify_password
from db.accounts import create_business, get_business_by_email

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=200)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    status: str


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterBody) -> UserOut:
    if get_business_by_email(str(body.email)) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    bid = create_business(
        email=str(body.email),
        password_hash=hash_password(body.password),
        name=body.name.strip(),
        role="business",
        status="pending",
    )
    logger.info("business_registered id=%s email=%s", bid, body.email)
    row = get_business_by_email(str(body.email))
    assert row is not None
    return UserOut(
        id=int(row["id"]),
        email=str(row["email"]),
        name=str(row["name"]),
        role=str(row["role"]),
        status=str(row["status"]),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginBody) -> TokenResponse:
    row = get_business_by_email(str(body.email))
    if row is None or not verify_password(body.password, str(row["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(
        user_id=int(row["id"]),
        role=str(row["role"]),
        email=str(row["email"]),
    )
    logger.info("login user_id=%s role=%s", row["id"], row["role"])
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        status=user.status,
    )
