"""Add administrator, sessions, productivity data, and dashboard preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def entry_columns():
    return (
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("priority", sa.String(6), nullable=False),
        sa.Column("completed", sa.Boolean, nullable=False),
        sa.Column("kindle_visible", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "administrator",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
    )
    op.create_table(
        "administrator_session",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("admin_id", sa.Integer, sa.ForeignKey("administrator.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.Integer, nullable=False),
    )
    op.create_index("ix_administrator_session_expires_at", "administrator_session", ["expires_at"])
    op.create_table(
        "dashboard_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("preferences", sa.JSON, nullable=False),
    )
    op.create_table("task", *entry_columns(), sa.Column("due_date", sa.Date),
                    sa.Column("position", sa.Integer, nullable=False))
    op.create_table("deadline", *entry_columns(), sa.Column("due_date", sa.Date, nullable=False),
                    sa.Column("due_time", sa.Time), sa.Column("archived", sa.Boolean, nullable=False))
    op.create_index("ix_deadline_due_date", "deadline", ["due_date"])


def downgrade() -> None:
    for table in ("deadline", "task", "dashboard_settings", "administrator_session", "administrator"):
        op.drop_table(table)
