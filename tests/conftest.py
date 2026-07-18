"""Shared test fixtures.

The tricky part of async FastAPI testing is the event loop. We use NullPool
(configured in app.database when TESTING=1) so no DB connection is ever reused
across event loops, and we create the schema once per session using a fresh,
isolated engine. The get_db dependency is overridden to use a NullPool session.
"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio

# These must be set before importing the app so config picks them up.
os.environ.setdefault("TESTING", "1")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/appdb_test",
)
os.environ.setdefault("JWT_SECRET", "test-secret")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402

TestSession = async_sessionmaker(
    create_async_engine(settings.database_url, poolclass=NullPool),
    expire_on_commit=False,
    class_=AsyncSession,
)


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    async def _init() -> None:
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_init())
    yield


async def _override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _register_and_login(ac: AsyncClient, tag: str) -> str:
    email = f"{tag}_{uuid.uuid4().hex[:10]}@example.com"
    password = "Str0ngPassw0rd!"
    r = await ac.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = await ac.post("/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def auth_client(client):
    token = await _register_and_login(client, "user")
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest_asyncio.fixture
async def admin_client(client):
    email = f"admin_{uuid.uuid4().hex[:10]}@example.com"
    password = "Str0ngPassw0rd!"
    await client.post("/auth/register", json={"email": email, "password": password})
    # Promote directly in the DB (there is no self-service path to admin).
    async with TestSession() as session:
        user = await session.scalar(select(User).where(User.email == email))
        user.role = Role.admin
        await session.commit()
    r = await client.post("/auth/token", data={"username": email, "password": password})
    client.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return client
