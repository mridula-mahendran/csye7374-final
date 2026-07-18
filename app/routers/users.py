"""User endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, operation_id="get_me")
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
