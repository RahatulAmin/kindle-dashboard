"""Persist prayer settings and monthly schedules."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prayer_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("preferences", sa.JSON, nullable=False),
    )
    op.create_table(
        "prayer_month",
        sa.Column("calculation", sa.String(64), primary_key=True),
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("days", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("prayer_month")
    op.drop_table("prayer_settings")
