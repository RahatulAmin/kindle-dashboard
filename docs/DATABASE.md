# SQLite and Alembic

Startup applies the Alembic upgrade before serving requests. Revision `0001` establishes Alembic bookkeeping. Revision `0002` adds administrator accounts and sessions, tasks, deadlines, and dashboard preferences. An immediate SQLite transaction serializes upgrades and preserves the existing database if an upgrade fails. Future SQLAlchemy models should inherit the shared Base in `app.db.database`, live in domain modules and be imported by the Alembic environment before autogeneration. SQLAlchemy connections enforce foreign keys. Request code should acquire sessions with a context manager and keep write transactions short. Operate one application replica while startup owns migration.

From the project root, check or apply the revision explicitly using the same settings as the app.

```bash
.venv/bin/alembic -c backend/alembic.ini current
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

For a future schema change, generate a revision with `revision --autogenerate -m "description"`, review its upgrade and downgrade, and rehearse the upgrade on a backup copy. Back up the live database before changing versions. Stop the application before a manual upgrade or restore and restart only after validating the result.

For an online backup, use the SQLite backup API, which captures a consistent database even if SQLite has a journal. With the default paths, run this from the project checkout after the database exists.

```bash
bash scripts/prepare-storage.sh
PYTHONPATH=backend .venv/bin/python - <<'PY'
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from app.core.config import Settings

settings = Settings()
stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
backup = settings.persistent_data_dir / "backups" / f"dashboard-{stamp}.sqlite3"
with closing(sqlite3.connect(settings.sqlite_path.as_uri() + "?mode=ro", uri=True)) as source:
    with closing(sqlite3.connect(backup)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise SystemExit("Backup failed integrity check")
print(backup)
PY
```

For restore, stop the application, preserve the current database and any `-wal`, `-shm`, and `-journal` sidecars together under a separate recovery directory, and copy the verified backup to the configured database path. Start the matching application version and confirm the migration revision and health response. Media will require separate backups when uploads are implemented.

## Scheduled daily backups and restoration

The permanent deployment runs `app.backup_database` through a systemd user timer. The job verifies each SQLite copy, publishes it atomically, and keeps the most recent 14 daily backups. See [deployment management](DEPLOYMENT.md#management-and-backups).

For a timestamped snapshot before a future deployment, run from the checkout:

```bash
set -a
. ../config/dashboard.env
set +a
umask 077
PYTHONPATH=backend .venv/bin/python -m app.backup_database --snapshot
```

To restore:

1. Stop the permanent application, backup service, and timer using the [rollback commands](DEPLOYMENT.md#rollback). Keep the source backup read-only. Run SQLite `PRAGMA integrity_check` on the chosen backup and require the result `ok`.
2. Move the current database and any SQLite sidecars together into a separate private recovery directory. A previous journal must stay with the database it belongs to.
3. Copy the verified backup to the configured database path with mode 600 and ownership of the service account. Confirm that its Alembic revision matches the app you will start.
4. Start the application and backup timer. Check health and verify the expected tasks, deadlines, settings, and administrator login before discarding the recovery copy.
