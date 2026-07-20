"""Authentication endpoints: user registration and token issuance."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="register_user",
    responses={
        409: {"description": "Email already registered"},
        400: {"description": "Malformed request body"},
    },
)
async def register(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/token",
    response_model=Token,
    operation_id="login",
    responses={
        401: {"description": "Incorrect email or password"},
        400: {"description": "Malformed request body"},
    },
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    invalid = HTTPException(
        status_code=401,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # The login form takes a raw username (it does not go through SafeStr). A NUL
    # byte can never match a stored email and would raise at the DB driver
    # (asyncpg rejects NUL in text), so fail the login cleanly instead of 500ing.
    if "\x00" in form.username:
        raise invalid
    user = await db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise invalid
    token = create_access_token(sub=str(user.id), role=user.role.value)
    return Token(access_token=token)
