from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime
from sqlalchemy import func, select

from app.models.dashboard import Deadline, Task
from app.schemas.api import ErrorResponse
from app.schemas.assistant import Data, DeadlineChange, EntryFilters, TaskChange
from app.schemas.dashboard import DeadlineInput, DeadlineOutput, Preferences, TaskInput, TaskOutput
from app.services.assistant import TokenIdentity, allow_scope
from app.services.auth import DB, require_admin
from app.services.dashboard import deadline_output, deadline_query, preferences, save_preferences, task_query
from app.services.entry_sync import change_entry, delete_entry, filtered, find

router = APIRouter(prefix="/api/v1")
ADMIN_ONLY = [Depends(require_admin)]
READ_ERRORS = {422: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 429: {"model": ErrorResponse}}
ITEM_ERRORS = {**READ_ERRORS, 404: {"model": ErrorResponse}}
CONFLICT = {"model": ErrorResponse, "headers": {
    "Link": {"description": "Latest item URL when available", "schema": {"type": "string"}},
    "ETag": {"description": "Latest updated_at version when available", "schema": {"type": "string"}},
}}
WRITE_ERRORS = {**ITEM_ERRORS, 409: CONFLICT, 413: {"model": ErrorResponse}}
DELETE_ERRORS = {**ITEM_ERRORS, 409: CONFLICT}
Filters = Annotated[EntryFilters, Query()]
TaskReader = Annotated[TokenIdentity | None, Depends(allow_scope("tasks:read"))]
TaskWriter = Annotated[TokenIdentity | None, Depends(allow_scope("tasks:write"))]
TaskDeleter = Annotated[TokenIdentity | None, Depends(allow_scope("tasks:delete"))]
DeadlineReader = Annotated[TokenIdentity | None, Depends(allow_scope("deadlines:read"))]
DeadlineWriter = Annotated[TokenIdentity | None, Depends(allow_scope("deadlines:write"))]
DeadlineDeleter = Annotated[TokenIdentity | None, Depends(allow_scope("deadlines:delete"))]


@router.get("/tasks", response_model=Data[list[TaskOutput]], responses=READ_ERRORS)
def tasks(db: DB, filters: Filters, _access: TaskReader):
    """List tasks. Bearer scope: tasks:read."""
    return {"data": list(db.scalars(filtered(task_query(), Task, filters)))}


@router.get("/tasks/{item_id}", response_model=Data[TaskOutput], responses=ITEM_ERRORS)
def get_task(item_id: int, db: DB, _access: TaskReader):
    """Retrieve a task. Bearer scope: tasks:read."""
    return {"data": find(db, Task, item_id)}


@router.post("/tasks", status_code=201, response_model=Data[TaskOutput],
             responses={**WRITE_ERRORS, 200: {"model": Data[TaskOutput]}})
def create_task(data: TaskChange, db: DB, token: TaskWriter, response: Response):
    """Create or synchronize a task. Bearer scope: tasks:write."""
    item, created = change_entry(db, Task, TaskInput, "task", data, token)
    response.status_code = 201 if created else 200
    return {"data": item}


@router.put("/tasks/{item_id}", response_model=Data[TaskOutput], responses=WRITE_ERRORS)
def edit_task(item_id: int, data: TaskChange, db: DB, token: TaskWriter):
    """Update a task. Set completed to true or false to complete or reopen it. Bearer scope: tasks:write."""
    item, _ = change_entry(db, Task, TaskInput, "task", data, token, item_id)
    return {"data": item}


@router.delete("/tasks/{item_id}", status_code=204, responses=DELETE_ERRORS)
def delete_task(item_id: int, db: DB, token: TaskDeleter, expected_updated_at: AwareDatetime | None = None):
    """Delete a task. Bearer scope: tasks:delete."""
    delete_entry(db, Task, "task", item_id, token, expected_updated_at)


@router.get("/deadlines", response_model=Data[list[DeadlineOutput]], responses=READ_ERRORS)
def deadlines(db: DB, filters: Filters, _access: DeadlineReader):
    """List deadlines, including archived entries. Bearer scope: deadlines:read."""
    return {"data": [deadline_output(item) for item in db.scalars(filtered(deadline_query(), Deadline, filters))]}


@router.get("/deadlines/{item_id}", response_model=Data[DeadlineOutput], responses=ITEM_ERRORS)
def get_deadline(item_id: int, db: DB, _access: DeadlineReader):
    """Retrieve a deadline. Bearer scope: deadlines:read."""
    return {"data": deadline_output(find(db, Deadline, item_id))}


@router.post("/deadlines", status_code=201, response_model=Data[DeadlineOutput],
             responses={**WRITE_ERRORS, 200: {"model": Data[DeadlineOutput]}})
def create_deadline(data: DeadlineChange, db: DB, token: DeadlineWriter, response: Response):
    """Create or synchronize a deadline. Bearer scope: deadlines:write."""
    item, created = change_entry(db, Deadline, DeadlineInput, "deadline", data, token)
    response.status_code = 201 if created else 200
    return {"data": deadline_output(item)}


@router.put("/deadlines/{item_id}", response_model=Data[DeadlineOutput], responses=WRITE_ERRORS)
def edit_deadline(item_id: int, data: DeadlineChange, db: DB, token: DeadlineWriter):
    """Update, archive, complete or reopen a deadline. Bearer scope: deadlines:write."""
    item, _ = change_entry(db, Deadline, DeadlineInput, "deadline", data, token, item_id)
    return {"data": deadline_output(item)}


@router.delete("/deadlines/{item_id}", status_code=204, responses=DELETE_ERRORS)
def delete_deadline(item_id: int, db: DB, token: DeadlineDeleter, expected_updated_at: AwareDatetime | None = None):
    """Delete a deadline. Bearer scope: deadlines:delete."""
    delete_entry(db, Deadline, "deadline", item_id, token, expected_updated_at)


@router.get("/settings", dependencies=ADMIN_ONLY)
def get_settings(db: DB):
    return {"data": preferences(db)}


@router.put("/settings", dependencies=ADMIN_ONLY)
def put_settings(data: Preferences, db: DB):
    save_preferences(db, data)
    return {"data": data}


@router.get("/weather", dependencies=ADMIN_ONLY)
def get_weather(request: Request, db: DB):
    location = preferences(db).weather
    db.rollback()
    return {"data": {"location": location.name, "weather": request.app.state.weather.get(location)}}


@router.get("/overview", dependencies=ADMIN_ONLY)
def overview(db: DB):
    return {"data": {
        "open_tasks": db.scalar(select(func.count()).select_from(Task).where(Task.completed.is_(False))),
        "active_deadlines": db.scalar(select(func.count()).select_from(Deadline).where(
            Deadline.archived.is_(False), Deadline.completed.is_(False))),
    }}
