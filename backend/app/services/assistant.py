import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import HTTPException, Request, Response, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.models.assistant import ApiAudit, ApiToken
from app.models.dashboard import utc_timestamp
from app.services.auth import COOKIE, DB, SAFE_METHODS, require_admin_session, supplies_bearer, token_digest

SCOPES = frozenset({
    "tasks:read", "tasks:write", "tasks:delete",
    "deadlines:read", "deadlines:write", "deadlines:delete",
    "briefing:read", "briefing:write",
})
BEARER = HTTPBearer(
    scheme_name="AssistantBearer", bearerFormat="Opaque",
    description="Scoped external API token issued by the terminal CLI.", auto_error=False,
)
ADMIN_COOKIE = APIKeyCookie(
    name=COOKIE, scheme_name="AdminSession", auto_error=False,
    description="Browser administrator session. Mutations also require the X-CSRF-Token header.",
)
TOKEN_FORMAT = re.compile(r"kda_[A-Za-z0-9_-]{43}")


@dataclass(frozen=True)
class TokenIdentity:
    id: int
    name: str


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def allow_scope(scope: str):
    def authorize(request: Request, response: Response, db: DB,
                  credential: Annotated[HTTPAuthorizationCredentials | None, Security(BEARER)],
                  _cookie: Annotated[str | None, Security(ADMIN_COOKIE)]) -> TokenIdentity | None:
        response.headers["Cache-Control"] = "no-store"
        if not supplies_bearer(request):
            require_admin_session(request, response, db)
            return None

        request.app.state.assistant_limiter.check(
            request.client.host if request.client else "unknown", "Too many API requests. Try again in a minute.",
        )
        headers = {"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"}
        if (credential is None or len(request.headers.getlist("authorization")) != 1
                or not TOKEN_FORMAT.fullmatch(credential.credentials)):
            raise HTTPException(401, "Invalid or inactive API token.", headers=headers)

        # Serialize token state, optimistic version checks, mutation and audit with other SQLite writers.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        record = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_digest(credential.credentials)))
        now = utc_timestamp()
        if not record or record.revoked or (record.expires_at is not None and record.expires_at <= now):
            raise HTTPException(401, "Invalid or inactive API token.", headers=headers)
        if scope not in record.scopes:
            raise HTTPException(403, f"API token requires {scope}.", headers={"Cache-Control": "no-store"})
        identity = TokenIdentity(record.id, record.name)
        record.last_used_at = now
        if request.method in SAFE_METHODS:
            db.commit()
        return identity
    return authorize


def audit(db, token: TokenIdentity | None, action: str, resource: str, resource_id: int, fields=()) -> None:
    if token is not None:
        db.add(ApiAudit(token_id=token.id, token_name=token.name, action=action,
                        resource_type=resource, resource_id=resource_id, changed_fields=sorted(fields)))
