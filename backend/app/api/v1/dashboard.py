from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select

from app.models.dashboard import Deadline, Task
from app.schemas.dashboard import DeadlineInput, TaskInput, TaskOutput, Preferences
from app.services.auth import DB, require_admin
from app.services.dashboard import deadline_output, deadline_query, preferences, save_preferences, task_query

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_admin)])


def find(db, model, item_id):
    record = db.get(model, item_id)
    if record is None:
        raise HTTPException(404, "This entry no longer exists.")
    return record


def update(db, record, data):
    for key, value in data.model_dump().items():
        setattr(record, key, value)
    db.commit()
    return record


@router.get("/tasks")
def tasks(db: DB):
    return {"data": [TaskOutput.model_validate(item) for item in db.scalars(task_query())]}


@router.post("/tasks", status_code=201)
def create_task(data: TaskInput, db: DB):
    item = Task(**data.model_dump())
    db.add(item)
    db.commit()
    return {"data": TaskOutput.model_validate(item)}


@router.put("/tasks/{item_id}")
def edit_task(item_id: int, data: TaskInput, db: DB):
    return {"data": TaskOutput.model_validate(update(db, find(db, Task, item_id), data))}


@router.delete("/tasks/{item_id}", status_code=204)
def delete_task(item_id: int, db: DB):
    db.delete(find(db, Task, item_id))
    db.commit()


@router.get("/deadlines")
def deadlines(db: DB):
    return {"data": [deadline_output(item) for item in db.scalars(deadline_query())]}


@router.post("/deadlines", status_code=201)
def create_deadline(data: DeadlineInput, db: DB):
    item = Deadline(**data.model_dump())
    db.add(item)
    db.commit()
    return {"data": deadline_output(item)}


@router.put("/deadlines/{item_id}")
def edit_deadline(item_id: int, data: DeadlineInput, db: DB):
    return {"data": deadline_output(update(db, find(db, Deadline, item_id), data))}


@router.delete("/deadlines/{item_id}", status_code=204)
def delete_deadline(item_id: int, db: DB):
    db.delete(find(db, Deadline, item_id))
    db.commit()


@router.get("/settings")
def get_settings(db: DB):
    return {"data": preferences(db)}


@router.put("/settings")
def put_settings(data: Preferences, db: DB):
    save_preferences(db, data)
    return {"data": data}


@router.get("/weather")
def get_weather(request: Request, db: DB):
    location = preferences(db).weather
    db.rollback()
    return {"data": {"location": location.name, "weather": request.app.state.weather.get(location)}}


@router.get("/overview")
def overview(db: DB):
    return {"data": {
        "open_tasks": db.scalar(select(func.count()).select_from(Task).where(Task.completed.is_(False))),
        "active_deadlines": db.scalar(select(func.count()).select_from(Deadline).where(
            Deadline.archived.is_(False), Deadline.completed.is_(False))),
    }}
