"""Pydantic v2 schemas for request validation and response serialization."""

from datetime import datetime
from typing import Annotated

from email_validator import validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models import Role, Status


def _to_ascii_email(value: str) -> str:
    """Return the ASCII (punycode) form of an email address.

    Pydantic's ``EmailStr`` normalizes internationalized domains to Unicode
    (``foo@hz.xn--h2brj9c`` -> ``foo@hz.भारत``). That value then violates the
    response's own ``format: email`` contract, which expects an ASCII address.
    Storing and returning the ASCII form keeps the API consistent with its
    schema and makes stored emails canonical for login lookups.
    """
    return validate_email(value, check_deliverability=False).ascii_email or value


# EmailStr validates and normalizes; the AfterValidator then pins it to ASCII.
# The JSON schema stays ``{type: string, format: email}``.
AsciiEmail = Annotated[EmailStr, AfterValidator(_to_ascii_email)]


def _reject_unstorable(value: str) -> str:
    """Reject strings Postgres/asyncpg cannot persist.

    A NUL byte (0x00) or a lone UTF-16 surrogate raises at the database driver
    on INSERT, which surfaces as a 500. Rejecting them here turns those inputs
    into a clean 422 validation error. Normal non-ASCII text is unaffected.
    """
    if "\x00" in value:
        raise ValueError("must not contain NUL (0x00) characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("must be valid UTF-8 text") from exc
    return value


# A str that is guaranteed safe to store in Postgres. The validator only runs on
# the str branch, so `SafeStr | None` leaves None untouched.
SafeStr = Annotated[str, AfterValidator(_reject_unstorable)]


class UserCreate(BaseModel):
    email: AsciiEmail
    password: SafeStr = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: AsciiEmail
    role: Role
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TaskCreate(BaseModel):
    title: SafeStr = Field(min_length=1, max_length=200)
    description: SafeStr | None = Field(default=None, max_length=2000)
    status: Status = Status.todo
    priority: int = Field(default=3, ge=1, le=5)


class TaskUpdate(BaseModel):
    title: SafeStr | None = Field(default=None, min_length=1, max_length=200)
    description: SafeStr | None = Field(default=None, max_length=2000)
    status: Status | None = None
    priority: int | None = Field(default=None, ge=1, le=5)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    description: str | None
    status: Status
    priority: int
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    items: list[TaskRead]
    total: int
    limit: int
    offset: int
