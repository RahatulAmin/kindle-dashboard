from contextlib import closing
from datetime import date, timedelta
import sqlite3
import stat

import pytest

from app.backup_database import RETENTION, backup_database


def test_online_backup_with_wal_and_daily_retention(tmp_path):
    source = tmp_path / "live.sqlite3"
    backups = tmp_path / "backups"
    backups.mkdir()
    for offset in range(RETENTION + 3):
        day = date(2000, 1, 1) + timedelta(days=offset)
        (backups / f"dashboard-{day}.sqlite3").touch()
    unrelated = backups / "legacy.sqlite3"
    unrelated.touch()
    with closing(sqlite3.connect(source)) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE fixture (name TEXT)")
        live.execute("INSERT INTO fixture VALUES ('test task')")
        live.commit()
        live.execute("INSERT INTO fixture VALUES ('uncommitted task')")
        daily = backup_database(source, backups)
    assert stat.S_IMODE(daily.stat().st_mode) == 0o600
    assert len(list(backups.glob("dashboard-*.sqlite3"))) == RETENTION
    assert unrelated.is_file()
    with closing(sqlite3.connect(daily)) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert restored.execute("SELECT name FROM fixture").fetchall() == [("test task",)]
    assert backup_database(source, backups) == daily


def test_snapshot_and_failed_source_do_not_drop_existing_backups(tmp_path):
    source = tmp_path / "live.sqlite3"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE fixture (id INTEGER)")
    snapshots = tmp_path / "backups" / "snapshots"
    snapshot = backup_database(source, snapshots, snapshot=True)
    with pytest.raises(sqlite3.OperationalError):
        backup_database(tmp_path / "missing.sqlite3", snapshots)
    assert set(snapshots.glob("dashboard-*.sqlite3")) == {snapshot}
    assert not list(snapshots.glob("*.part"))
