from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models.dashboard import DashboardSettings, Deadline, Task
from app.schemas.dashboard import DeadlineOutput, Preferences

TORONTO = ZoneInfo("America/Toronto")


def preferences(session: Session) -> Preferences:
    stored = session.get(DashboardSettings, 1)
    return Preferences.model_validate(stored.preferences) if stored else Preferences()


def save_preferences(session: Session, value: Preferences) -> None:
    statement = insert(DashboardSettings).values(id=1, preferences=value.model_dump(mode="json"))
    session.execute(statement.on_conflict_do_update(
        index_elements=[DashboardSettings.id],
        set_={"preferences": statement.excluded.preferences},
    ))
    session.commit()


def task_query():
    return select(Task).order_by(Task.position, Task.id)


def deadline_query():
    return select(Deadline).order_by(Deadline.due_date, Deadline.due_time.asc().nulls_last(), Deadline.id)


def days_until(due_date: date, today: date | None = None) -> int:
    return (due_date - (today or datetime.now(TORONTO).date())).days


def deadline_output(deadline: Deadline) -> DeadlineOutput:
    return DeadlineOutput.model_validate({
        **{key: getattr(deadline, key) for key in DeadlineOutput.model_fields if key != "days_until"},
        "days_until": days_until(deadline.due_date),
    })
