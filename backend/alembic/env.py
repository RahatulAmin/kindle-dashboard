from alembic import context

from app.core.config import Settings
from app.db.database import Base, Database

config = context.config


def run_online(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(dialect_name="sqlite", target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif (connection := config.attributes.get("connection")) is not None:
    run_online(connection)
else:
    database = Database(Settings().sqlite_path)
    try:
        database.path.parent.mkdir(parents=True, exist_ok=True)
        with database.engine.begin() as connection:
            run_online(connection)
    finally:
        database.close()
