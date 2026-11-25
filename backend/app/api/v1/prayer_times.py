from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.services.auth import DB, require_admin
from app.services.dashboard import TORONTO
from app.services.prayer_times import (
    METHODS, PRAYERS, PrayerPreferences, prayer_day, prayer_preferences, save_prayer_preferences,
)

router = APIRouter(prefix="/api/v1/prayer-times", dependencies=[Depends(require_admin)])


def status(db, config, now):
    result = prayer_day(db, config, now, include_update=True)
    return {"data": {
        "preferences": config,
        "methods": METHODS,
        "date": now.astimezone(TORONTO).date(),
        "today": dict(zip(PRAYERS, result.today, strict=True)),
        "last_updated_at": result.updated_at,
    }}


@router.get("")
def get_prayer_times(request: Request, db: DB, background: BackgroundTasks):
    config = prayer_preferences(db)
    now = datetime.now(UTC)
    result = status(db, config, now)
    db.rollback()
    if config.school is not None:
        background.add_task(request.app.state.prayers.refresh, request.app.state.database, config, now)
    return result


@router.put("")
def put_prayer_times(config: PrayerPreferences, request: Request, db: DB, background: BackgroundTasks):
    save_prayer_preferences(db, config)
    now = datetime.now(UTC)
    result = status(db, config, now)
    db.rollback()
    if config.school is not None:
        background.add_task(request.app.state.prayers.refresh, request.app.state.database, config, now)
    return result


@router.post("/refresh")
def refresh_prayer_times(request: Request, db: DB):
    config = prayer_preferences(db)
    db.rollback()
    if config.school is None:
        raise HTTPException(422, "Choose and save an Asr calculation first.")
    now = datetime.now(UTC)
    if not request.app.state.prayers.refresh(request.app.state.database, config, now, force=True):
        raise HTTPException(502, "AlAdhan could not refresh every month. Existing schedules were kept.")
    return status(db, prayer_preferences(db), datetime.now(UTC))
