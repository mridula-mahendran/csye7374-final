"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routers import admin, auth, tasks, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # For a teaching project we create tables on startup instead of running
    # Alembic migrations. Swap this for migrations in a real deployment.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Tasks API",
    version="1.0.0",
    description=(
        "A small but realistic task-management API used as the system under "
        "test for a CI/CD testing pipeline. Each pipeline stage is a distinct "
        "testing tool acting as a quality gate."
    ),
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"], operation_id="health")
async def health() -> dict:
    return {"status": "ok"}
