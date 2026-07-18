"""Async database engine, session factory, and the get_db dependency.

We use SQLAlchemy 2.0 async style with asyncpg. In test mode we switch to a
NullPool so each session opens a fresh connection on the current event loop,
which sidesteps the classic "attached to a different loop" errors that appear
when a pooled connection is reused across pytest-asyncio's per-test loops.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


engine_kwargs: dict = {"echo": False, "future": True}
if settings.testing:
    engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session
