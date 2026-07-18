"""Admin-only endpoints (RBAC demonstration)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_admin
from app.models import Task, User
from app.schemas import TaskList, TaskRead

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tasks", response_model=TaskList, operation_id="admin_list_tasks")
async def admin_list_tasks(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskList:
    total = await db.scalar(select(func.count()).select_from(Task))
    rows = (
        await db.scalars(select(Task).order_by(Task.id).limit(limit).offset(offset))
    ).all()
    return TaskList(
        items=[TaskRead.model_validate(row) for row in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
