"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI's default 422 handler echoes the raw offending input back in the
    # error body. Fuzzed inputs can contain lone UTF-16 surrogates, which are not
    # UTF-8 encodable, so rendering that echo crashes the response with a 500.
    # Drop `input`/`ctx` so the rejection is always a clean, serializable 422
    # (this also matches the documented HTTPValidationError schema exactly).
    cleaned = [
        {k: v for k, v in err.items() if k not in ("input", "ctx")}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(cleaned)})


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"], operation_id="health")
async def health() -> dict:
    return {"status": "ok"}
