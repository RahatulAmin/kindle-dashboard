"""Create the initial administrator from a trusted terminal."""
import argparse
from getpass import getpass

from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.database import Database
from app.models.dashboard import Admin
from app.services.auth import hash_password


def create_admin(database: Database, username: str, password: str) -> None:
    username = username.strip()
    if not 1 <= len(username) <= 64:
        raise ValueError("Use a username of 1 to 64 characters.")
    if not 12 <= len(password) <= 256:
        raise ValueError("Use a password of 12 to 256 characters.")
    with database.sessions() as session:
        if session.get(Admin, 1):
            raise ValueError("An administrator already exists.")
        session.add(Admin(id=1, username=username, password_hash=hash_password(password)))
        try:
            session.commit()
        except IntegrityError as exc:
            raise ValueError("An administrator already exists.") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    args = parser.parse_args()
    password = getpass("Administrator password: ")
    if password != getpass("Confirm password: "):
        parser.exit(1, "Passwords do not match.\n")
    database = Database(Settings().sqlite_path)
    try:
        database.migrate()
        create_admin(database, args.username, password)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    finally:
        database.close()
    print("Administrator created.")


if __name__ == "__main__":
    main()
