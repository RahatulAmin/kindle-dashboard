import hashlib
import hmac
import secrets
from collections import Counter, deque
from threading import BoundedSemaphore, Lock
from time import monotonic, time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.models.dashboard import AdminSession

COOKIE = "kindle_admin"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DUMMY_HASH = "00" * 16 + ":" + "00" * 64


def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=3, maxmem=64 * 1024**2)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + derive_key(password, salt).hex()


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split(":")
    return hmac.compare_digest(derive_key(password, bytes.fromhex(salt)), bytes.fromhex(digest))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return token_digest("csrf:" + token)


class LoginLimiter:
    def __init__(self, per_address: int = 5, total: int = 15):
        self.per_address = per_address
        self.total = total
        self.attempts: deque[tuple[float, str]] = deque()
        self.counts: Counter[str] = Counter()
        self.lock = Lock()
        self.hash_slots = BoundedSemaphore(2)

    def check(self, address: str, message: str = "Too many login attempts. Try again in a minute.") -> None:
        with self.lock:
            now = monotonic()
            while self.attempts and self.attempts[0][0] <= now - 60:
                _, expired_address = self.attempts.popleft()
                self.counts[expired_address] -= 1
                if not self.counts[expired_address]:
                    del self.counts[expired_address]
            if self.counts[address] >= self.per_address or len(self.attempts) >= self.total:
                raise HTTPException(429, message, headers={"Retry-After": "60", "Cache-Control": "no-store"})
            self.attempts.append((now, address))
            self.counts[address] += 1


def database_session(request: Request):
    with request.app.state.database.sessions() as session:
        yield session


DB = Annotated[Session, Depends(database_session)]


def session_record(request: Request, db: Session, now: int) -> AdminSession | None:
    token = request.cookies.get(COOKIE, "")
    if len(token) != 43 or not token.isascii():
        return None
    record = db.get(AdminSession, token_digest(token))
    return record if record and record.expires_at > now else None


def supplies_bearer(request: Request) -> bool:
    return any(value.split(maxsplit=1)[0].lower() == "bearer"
               for value in request.headers.getlist("authorization") if value.strip())


def deny_bearer(request: Request) -> None:
    if supplies_bearer(request):
        raise HTTPException(401, "This endpoint requires administrator sign-in.")


def require_admin(request: Request, response: Response, db: DB) -> AdminSession:
    deny_bearer(request)
    return require_admin_session(request, response, db)


def require_admin_session(request: Request, response: Response, db: DB) -> AdminSession:
    response.headers["Cache-Control"] = "no-store"
    record = session_record(request, db, int(time()))
    if not record:
        raise HTTPException(401, "Sign in as administrator.", headers={"Cache-Control": "no-store"})
    if request.method not in SAFE_METHODS:
        submitted = request.headers.get("X-CSRF-Token", "")
        if not submitted.isascii() or not hmac.compare_digest(submitted, csrf_token(request.cookies[COOKIE])):
            raise HTTPException(403, "Invalid CSRF token. Reload and try again.")
    return record


Authenticated = Annotated[AdminSession, Depends(require_admin)]
