import argparse
from contextlib import closing
from datetime import UTC, datetime
import fcntl
import os
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile

from app.core.config import Settings
from app.services.dashboard import TORONTO

DAILY_NAME = re.compile(r"dashboard-[0-9]{4}-[0-9]{2}-[0-9]{2}\.sqlite3")
RETENTION = 14


def backup_database(source: Path, directory: Path, *, snapshot: bool = False) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / ".backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if snapshot:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        else:
            stamp = datetime.now(TORONTO).date().isoformat()
        destination = directory / f"dashboard-{stamp}.sqlite3"
        with NamedTemporaryFile(prefix=".dashboard-", suffix=".part", dir=directory,
                                delete=False) as temporary_file:
            temporary = Path(temporary_file.name)
        try:
            with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as live:
                with closing(sqlite3.connect(temporary)) as copy:
                    live.backup(copy)
                    if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                        raise RuntimeError("SQLite backup failed its integrity check")
            with temporary.open("rb") as verified:
                os.fsync(verified.fileno())
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

        if not snapshot:
            daily = sorted((path for path in directory.iterdir() if DAILY_NAME.fullmatch(path.name)),
                           reverse=True)
            for path in daily[RETENTION:]:
                path.unlink()
        return destination


def main():
    parser = argparse.ArgumentParser(description="Create a verified online SQLite backup")
    parser.add_argument("--snapshot", action="store_true", help="Save a timestamped snapshot outside daily rotation")
    options = parser.parse_args()
    settings = Settings()
    directory = settings.persistent_data_dir / "backups"
    if options.snapshot:
        directory /= "snapshots"
    print(backup_database(settings.sqlite_path, directory, snapshot=options.snapshot))


if __name__ == "__main__":
    main()
