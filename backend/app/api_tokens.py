"""Issue, inspect and revoke scoped dashboard credentials from a trusted terminal."""

import argparse
from datetime import UTC, datetime
import json
import secrets

from sqlalchemy import inspect, select

from app.core.config import Settings
from app.db.database import Database
from app.models.assistant import ApiToken
from app.services.assistant import SCOPES, timestamp
from app.services.auth import token_digest


def scope_list(value: str) -> list[str]:
    scopes = set(value.split(","))
    if not scopes or scopes - SCOPES:
        raise argparse.ArgumentTypeError("Provide comma-separated scopes from: " + ", ".join(sorted(SCOPES)))
    return sorted(scopes)


def expiry(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
        if moment.utcoffset() is None or moment <= datetime.now(UTC):
            raise ValueError
        return timestamp(moment)
    except (ValueError, OverflowError) as error:
        raise argparse.ArgumentTypeError("Use a future ISO 8601 timestamp with an explicit timezone.") from error


def create_token(db, name: str, scopes: list[str], expires_at: str | None = None) -> tuple[int, str]:
    raw = "kda_" + secrets.token_urlsafe(32)
    record = ApiToken(name=name, token_hash=token_digest(raw), scopes=scopes, expires_at=expires_at)
    db.add(record)
    db.commit()
    return record.id, raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("name")
    create.add_argument("--scopes", required=True, type=scope_list)
    create.add_argument("--expires-at", type=expiry)
    commands.add_parser("list")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("id", type=int)
    options = parser.parse_args()
    if options.command == "create":
        options.name = options.name.strip()
        if not 1 <= len(options.name) <= 80 or not options.name.isprintable():
            parser.error("Use a printable token name of 1 to 80 characters.")

    path = Settings().sqlite_path
    if not path.is_file():
        parser.error("Initialize the database with migration 0004 before managing tokens.")
    database = Database(path)
    try:
        if not inspect(database.engine).has_table(ApiToken.__tablename__):
            parser.error("Apply migration 0004 before managing tokens.")
        with database.sessions() as db:
            if options.command == "create":
                identifier, raw = create_token(db, options.name, options.scopes, options.expires_at)
                print(f"Token ID: {identifier}\nBearer token (shown once): {raw}")
            elif options.command == "revoke":
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
                record = db.get(ApiToken, options.id)
                if not record:
                    parser.error("Token ID does not exist.")
                record.revoked = True
                db.commit()
                print(f"Revoked token {options.id}.")
            else:
                fields = ("id", "name", "scopes", "created_at", "last_used_at", "expires_at", "revoked")
                print(json.dumps([{field: getattr(row, field) for field in fields}
                                  for row in db.scalars(select(ApiToken).order_by(ApiToken.id))], indent=2))
    finally:
        database.close()


if __name__ == "__main__":
    main()
