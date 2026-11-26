from datetime import UTC, date, datetime, time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.models.assistant import ApiAudit, Briefing
from app.schemas.api import ErrorResponse
from app.schemas.assistant import AuditOutput, BriefingInput, BriefingOutput, Data
from app.services.assistant import TokenIdentity, allow_scope, audit, timestamp
from app.services.auth import DB, require_admin

router = APIRouter(prefix="/api/v1")
BriefingReader = Annotated[TokenIdentity | None, Depends(allow_scope("briefing:read"))]
BriefingWriter = Annotated[TokenIdentity | None, Depends(allow_scope("briefing:write"))]
READ_ERRORS = {422: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 429: {"model": ErrorResponse}}


@router.get("/briefing", response_model=Data[BriefingOutput | None], responses=READ_ERRORS)
def get_briefing(db: DB, _access: BriefingReader):
    """Return the current briefing, or null. Bearer scope: briefing:read."""
    return {"data": db.get(Briefing, 1)}


@router.post("/briefing", response_model=Data[BriefingOutput],
             responses={**READ_ERRORS, 413: {"model": ErrorResponse}})
def replace_briefing(data: BriefingInput, db: DB, token: BriefingWriter):
    """Replace the entire briefing. Bearer scope: briefing:write."""
    if token is None:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    record = db.get(Briefing, 1)
    values = data.model_dump()
    if record is None:
        record = Briefing(id=1, **values)
        db.add(record)
        changed = values.keys()
    else:
        changed = [field for field, value in values.items() if getattr(record, field) != value]
        for field in changed:
            setattr(record, field, values[field])
    if changed:
        audit(db, token, "replace", "briefing", 1, changed)
    db.commit()
    return {"data": record}


@router.delete("/briefing", dependencies=[Depends(require_admin)], status_code=204)
def clear_briefing(db: DB):
    """Clear the briefing from the web administration interface."""
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    record = db.get(Briefing, 1)
    if record:
        db.delete(record)
    db.commit()


@router.get("/audit", dependencies=[Depends(require_admin)], response_model=Data[list[AuditOutput]])
def audit_history(db: DB, token_id: Annotated[int | None, Query(ge=1)] = None,
                  action: Literal["create", "upsert", "update", "delete", "replace"] | None = None,
                  date_from: date | None = None, date_to: date | None = None,
                  before_id: Annotated[int | None, Query(ge=1)] = None,
                  limit: Annotated[int, Query(ge=1, le=200)] = 50):
    """List API mutation metadata. Date filters use UTC calendar days."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to.")
    query = select(ApiAudit)
    if token_id is not None:
        query = query.where(ApiAudit.token_id == token_id)
    if action is not None:
        query = query.where(ApiAudit.action == action)
    if date_from:
        query = query.where(ApiAudit.timestamp >= timestamp(datetime.combine(date_from, time.min, UTC)))
    if date_to:
        query = query.where(ApiAudit.timestamp <= timestamp(datetime.combine(date_to, time.max, UTC)))
    if before_id is not None:
        query = query.where(ApiAudit.id < before_id)
    return {"data": list(db.scalars(query.order_by(ApiAudit.id.desc()).limit(limit)))}
