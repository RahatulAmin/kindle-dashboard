import secrets
from time import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import StringConstraints
from sqlalchemy import delete

from app.models.dashboard import Admin, AdminSession
from app.schemas.dashboard import InputModel
from app.services.auth import (
    COOKIE, DUMMY_HASH, Authenticated, DB, csrf_token, deny_bearer, session_record,
    token_digest, verify_password,
)

router = APIRouter(prefix="/api/v1/auth", dependencies=[Depends(deny_bearer)])


class Credentials(InputModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


def identity(username: str, token: str) -> dict[str, str]:
    return {"username": username, "csrf_token": csrf_token(token)}


@router.get("/session")
def get_session(request: Request, response: Response, db: DB):
    response.headers["Cache-Control"] = "no-store"
    admin = db.get(Admin, 1)
    record = session_record(request, db, int(time()))
    return {"data": {
        "setup_required": admin is None,
        "administrator": identity(admin.username, request.cookies[COOKIE]) if admin and record else None,
    }}


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response, db: DB):
    if request.headers.get("X-Kindle-Admin") != "1":
        raise HTTPException(403, "Sign in from the administration page.")
    limiter = request.app.state.login_limiter
    limiter.check(request.client.host if request.client else "unknown")
    if not limiter.hash_slots.acquire(blocking=False):
        raise HTTPException(429, "Sign-in service is busy. Try again shortly.", headers={"Retry-After": "2"})
    try:
        admin = db.get(Admin, 1)
        matches = verify_password(credentials.password, admin.password_hash if admin else DUMMY_HASH)
    finally:
        limiter.hash_slots.release()
    if not admin or not matches or credentials.username != admin.username:
        raise HTTPException(401, "Invalid username or password.")
    now = int(time())
    ttl = request.app.state.settings.admin_session_ttl_seconds
    token = secrets.token_urlsafe(32)
    previous = session_record(request, db, now)
    if previous:
        db.delete(previous)
    db.execute(delete(AdminSession).where(AdminSession.expires_at <= now))
    db.add(AdminSession(token_hash=token_digest(token), admin_id=admin.id, expires_at=now + ttl))
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(COOKIE, token, path="/api/v1", max_age=ttl, httponly=True,
                        secure=request.app.state.settings.admin_cookie_secure, samesite="strict")
    return {"data": identity(admin.username, token)}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB, record: Authenticated):
    db.delete(record)
    db.commit()
    response.delete_cookie(COOKIE, path="/api/v1", httponly=True, samesite="strict",
                           secure=request.app.state.settings.admin_cookie_secure)
