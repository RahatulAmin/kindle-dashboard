from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(path)),
            connect_args={"timeout": 5},
        )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        event.listen(self.engine, "connect", self.enable_foreign_keys)

    @staticmethod
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        config = Config(str(BACKEND / "alembic.ini"))
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def close(self) -> None:
        self.engine.dispose()
