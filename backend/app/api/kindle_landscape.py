import base64
from dataclasses import asdict
from datetime import UTC, datetime
import hmac
import json
from time import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field, StrictBool
from sqlalchemy import func, select

from app.api.kindle_display import require_device
from app.models.assistant import Briefing
from app.models.dashboard import Task
from app.rendering.kindle import NO_CACHE
from app.rendering.landscape import TaskRow, render_landscape
from app.rendering.landscape_layout import (
    HEIGHT, TABS, WIDTH, Page, pagination_controls, row_box, tab_box, task_page_size,
)
from app.schemas.assistant import BriefingOutput
from app.schemas.dashboard import InputModel
from app.services.auth import DB
from app.services.dashboard import preferences, task_query
from app.services.prayer_times import prayer_day, prayer_preferences
from app.services.weather import Weather

router = APIRouter(prefix="/api/kindle/landscape", dependencies=[Depends(require_device)])
REFRESH_SECONDS = 30
FRAME_LIFETIME = 90


class Completion(InputModel):
    completed: StrictBool
    capability: str = Field(min_length=1, max_length=512)


def sharing(db):
    config = preferences(db)
    if not config.kindle_data_enabled:
        raise HTTPException(404, "Kindle dashboard data sharing is disabled.", headers=NO_CACHE)
    return config


def todo_enabled(config):
    return any(widget.key == "tasks" and widget.visible for widget in config.widgets)


def capability(key, task, frame_id, expires):
    data = json.dumps([frame_id, expires, task.id, task.created_at, task.updated_at, not task.completed],
                      separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(data).decode()
    return encoded + "." + hmac.digest(key, data, "sha256").hex()


def validate_capability(key, change, task_id):
    try:
        encoded, signature = change.capability.split(".", 1)
        data = base64.b64decode(encoded, altchars=b"-_", validate=True)
        if hmac.compare_digest(hmac.digest(key, data, "sha256").hex().encode(), signature.encode()):
            _, expires, bound_id, created_at, updated_at, desired = json.loads(data)
            if expires >= time() and bound_id == task_id and desired is change.completed:
                return created_at, updated_at
    except (TypeError, ValueError):
        pass
    raise HTTPException(409, "Refresh the dashboard before updating this task.", headers=NO_CACHE)


@router.get("/frame")
def landscape_frame(request: Request, db: DB, background: BackgroundTasks, page: Page = "todo",
                    number: Annotated[int, Query(ge=1, le=2_147_483_647)] = 1,
                    battery: Annotated[int | None, Header(alias="percent-charged", ge=0, le=100)] = None,
                    wifi: Annotated[str | None, Header(alias="dashboard-wifi")] = None):
    # Keep the count and rows on one SQLite read snapshot, then release it before weather and drawing.
    db.connection().exec_driver_sql("BEGIN")
    config = sharing(db)
    now = datetime.now(UTC)
    salat = prayer_preferences(db)
    prayers = prayer_day(db, salat, now) if salat.enabled else None
    page_size = task_page_size(salat.enabled)
    frame_id = uuid4().hex
    expires = int(time()) + FRAME_LIFETIME
    key = request.app.state.landscape_signing_key
    regions = [
        {**asdict(tab_box(index)), "action": "navigate", "page": tab, "number": 1}
        for index, tab in enumerate(TABS)
    ]
    tasks = []
    page_count, page_number = 1, 1
    if page == "todo" and todo_enabled(config):
        visible = Task.kindle_visible.is_(True)
        count = db.scalar(select(func.count()).select_from(Task).where(visible))
        page_count = max(1, (count + page_size - 1) // page_size)
        page_number = min(number, page_count)
        query = task_query().where(visible).offset((page_number - 1) * page_size).limit(page_size)
        for index, task in enumerate(db.scalars(query)):
            tasks.append(TaskRow(task.title, task.completed, task.priority, task.due_date))
            regions.append({
                **asdict(row_box(index)), "action": "complete", "task_id": task.id,
                "completed": not task.completed, "capability": capability(key, task, frame_id, expires),
            })
        for target, hit, _, _ in pagination_controls(page_number, page_count, salat.enabled):
            regions.append({**asdict(hit), "action": "navigate", "page": page, "number": target})
    briefing = None
    if page == "todo" and any(widget.key == "briefing" and widget.visible for widget in config.widgets):
        record = db.get(Briefing, 1)
        if record is not None:
            briefing = BriefingOutput.model_validate(record)
    db.rollback()
    if salat.enabled:
        background.add_task(request.app.state.prayers.refresh, request.app.state.database, salat, now)
    weather = Weather("unavailable")
    if any(widget.key == "weather" and widget.visible for widget in config.widgets):
        weather = request.app.state.weather.get(config.weather)
    png = render_landscape(page, now, config.weather.name, weather, tasks,
                           page_number, page_count, battery=battery, wifi=wifi == "connected",
                           prayers=prayers, briefing=briefing)
    return JSONResponse({
        "filename": f"landscape-{frame_id}.png", "width": WIDTH, "height": HEIGHT,
        "refresh_rate": REFRESH_SECONDS, "page": page, "number": page_number,
        "png": base64.b64encode(png).decode("ascii"), "regions": regions,
    }, headers=NO_CACHE)


@router.put("/tasks/{task_id}/completion", status_code=204)
def set_completion(task_id: int, change: Completion, request: Request, db: DB) -> Response:
    # Serialize visibility, version and state checks with concurrent admin writes.
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    if not todo_enabled(sharing(db)):
        raise HTTPException(404, "Task unavailable.", headers=NO_CACHE)
    task = db.get(Task, task_id)
    if task is None or not task.kindle_visible:
        raise HTTPException(404, "Task unavailable.", headers=NO_CACHE)
    created_at, updated_at = validate_capability(request.app.state.landscape_signing_key, change, task_id)
    if task.created_at != created_at or (task.completed != change.completed and task.updated_at != updated_at):
        raise HTTPException(409, "Refresh the dashboard before updating this task.", headers=NO_CACHE)
    if task.completed != change.completed:
        task.completed = change.completed
        db.commit()
    return Response(status_code=204, headers=NO_CACHE)
