"""Add scoped assistant tokens, synchronization metadata, audit and briefing."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

settings = sa.table("dashboard_settings", sa.column("id", sa.Integer), sa.column("preferences", sa.JSON))


def update_widget(add: bool) -> None:
    connection = op.get_bind()
    for row in connection.execute(sa.select(settings)).all():
        value = row.preferences
        widgets = value.get("widgets")
        if widgets is None:
            continue
        next_widgets = [widget for widget in widgets if widget["key"] != "briefing"]
        if add:
            next_widgets.append({"key": "briefing", "visible": False, "limit": 1})
        connection.execute(settings.update().where(settings.c.id == row.id)
                           .values(preferences={**value, "widgets": next_widgets}))


def upgrade() -> None:
    for table in ("task", "deadline"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("source", sa.String(80)))
            batch.add_column(sa.Column("external_ref", sa.String(160)))
            batch.create_check_constraint(f"ck_{table}_external_pair", "(source IS NULL) = (external_ref IS NULL)")
            batch.create_index(f"ix_{table}_external_identity", ["source", "external_ref"], unique=True)
            batch.create_index(f"ix_{table}_external_ref", ["external_ref"])
            batch.create_index(f"ix_{table}_updated_at", ["updated_at"])
            if table == "task":
                batch.create_index("ix_task_due_date", ["due_date"])

    op.create_table(
        "api_token",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", sa.JSON, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("last_used_at", sa.String(40)),
        sa.Column("expires_at", sa.String(40)),
        sa.Column("revoked", sa.Boolean, nullable=False),
    )
    op.create_table(
        "api_audit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_id", sa.Integer, sa.ForeignKey("api_token.id"), nullable=False),
        sa.Column("token_name", sa.String(80), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Integer, nullable=False),
        sa.Column("timestamp", sa.String(40), nullable=False),
        sa.Column("changed_fields", sa.JSON, nullable=False),
    )
    op.create_index("ix_api_audit_token_timestamp", "api_audit", ["token_id", "timestamp"])
    op.create_index("ix_api_audit_action", "api_audit", ["action"])
    op.create_index("ix_api_audit_timestamp", "api_audit", ["timestamp"])
    op.create_table(
        "briefing",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("lines", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_briefing_singleton"),
    )
    update_widget(add=True)


def downgrade() -> None:
    update_widget(add=False)
    op.drop_table("briefing")
    op.drop_table("api_audit")
    op.drop_table("api_token")
    for table in ("task", "deadline"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_updated_at")
            batch.drop_index(f"ix_{table}_external_identity")
            batch.drop_index(f"ix_{table}_external_ref")
            if table == "task":
                batch.drop_index("ix_task_due_date")
            batch.drop_constraint(f"ck_{table}_external_pair", type_="check")
            batch.drop_column("external_ref")
            batch.drop_column("source")
