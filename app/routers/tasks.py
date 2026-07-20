"""Task resource endpoints.

Notable design choices that matter for the testing pipeline:

* POST /tasks declares OpenAPI ``links`` and returns a ``Location`` header so
  Schemathesis can chain create -> get/update/delete during stateful testing.
* Explicit ``operation_id`` values are set so those links resolve cleanly.
* ``_get_owned_task`` centralizes the authorization check. Removing it is the
  IDOR demo (Bug 2): the example-based authorization tests catch it, while
  Schemathesis (single identity, schema-valid responses) structurally cannot.
* GET /tasks/stats is declared before GET /tasks/{task_id} and uses the pure
  ``is_actionable`` rule, which is the mutation-testing target (Bug 3).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Status, Task, User
from app.rules import is_actionable
from app.schemas import TaskCreate, TaskList, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Postgres INTEGER upper bound. Path/query ids above this overflow the column and
# would surface as a 500 (asyncpg NumericValueOutOfRange); we reject them as 422
# validation errors instead so the API never returns a server error for them.
MAX_INT = 2_147_483_647

# Error responses declared on the operations so the OpenAPI contract matches the
# API's real behavior. Without these, Schemathesis' status_code_conformance check
# fails: the app legitimately returns these codes but the schema never mentions them.
TASK_NOT_FOUND: dict = {404: {"description": "Task not found"}}
MALFORMED_BODY: dict = {400: {"description": "Malformed request body"}}

# OpenAPI links attached to the 201 response of create_task. Schemathesis reads
# these to build stateful workflows (create -> get -> update -> delete).
CREATE_LINKS = {
    "GetTask": {
        "operationId": "get_task",
        "parameters": {"task_id": "$response.body#/id"},
        "description": "Retrieve the task that was just created.",
    },
    "UpdateTask": {
        "operationId": "update_task",
        "parameters": {"task_id": "$response.body#/id"},
        "description": "Update the task that was just created.",
    },
    "DeleteTask": {
        "operationId": "delete_task",
        "parameters": {"task_id": "$response.body#/id"},
        "description": "Delete the task that was just created.",
    },
}


async def _get_owned_task(task_id: int, user: User, db: AsyncSession) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    # Authorization: an owner may touch their own tasks; an admin may touch any.
    # We return 404 (not 403) so we do not reveal that the id exists.
    # if task.owner_id != user.id and user.role != Role.admin:
    #     raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_task",
    responses={201: {"description": "Task created", "links": CREATE_LINKS}, **MALFORMED_BODY},
)
async def create_task(
    payload: TaskCreate,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    task = Task(owner_id=user.id, **payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    response.headers["Location"] = f"/tasks/{task.id}"
    return task


@router.get("", response_model=TaskList, operation_id="list_tasks")
async def list_tasks(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_INT)] = 0,
) -> TaskList:
    base = select(Task).where(Task.owner_id == user.id)
    if status_filter is not None:
        base = base.where(Task.status == status_filter)

    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.scalars(base.order_by(Task.id).limit(limit).offset(offset))
    ).all()
    return TaskList(
        items=[TaskRead.model_validate(row) for row in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", operation_id="task_stats")
async def task_stats(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    rows = (await db.scalars(select(Task).where(Task.owner_id == user.id))).all()
    actionable = sum(1 for task in rows if is_actionable(task))
    return {"total": len(rows), "actionable": actionable}


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    operation_id="get_task",
    responses=TASK_NOT_FOUND,
)
async def get_task(
    task_id: Annotated[int, Path(ge=1, le=MAX_INT)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    return await _get_owned_task(task_id, user, db)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    operation_id="update_task",
    responses={**TASK_NOT_FOUND, **MALFORMED_BODY},
)
async def update_task(
    task_id: Annotated[int, Path(ge=1, le=MAX_INT)],
    payload: TaskUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    task = await _get_owned_task(task_id, user, db)
    # exclude_unset ignores fields the client did not send. We also skip explicit
    # nulls: the update schema types these fields as optional, but the columns are
    # NOT NULL, so setting one to null would raise an IntegrityError (a 500).
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_task",
    responses=TASK_NOT_FOUND,
)
async def delete_task(
    task_id: Annotated[int, Path(ge=1, le=MAX_INT)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    task = await _get_owned_task(task_id, user, db)
    await db.delete(task)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
