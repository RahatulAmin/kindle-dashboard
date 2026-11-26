from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.dashboard import utc_timestamp


class ApiToken(Base):
    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=utc_timestamp)
    last_used_at: Mapped[str | None] = mapped_column(String(40))
    expires_at: Mapped[str | None] = mapped_column(String(40))
    revoked: Mapped[bool] = mapped_column(default=False)


class ApiAudit(Base):
    __tablename__ = "api_audit"
    __table_args__ = (Index("ix_api_audit_token_timestamp", "token_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("api_token.id"))
    token_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(20), index=True)
    resource_type: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[int]
    timestamp: Mapped[str] = mapped_column(String(40), default=utc_timestamp, index=True)
    changed_fields: Mapped[list[str]] = mapped_column(JSON)


class Briefing(Base):
    __tablename__ = "briefing"
    __table_args__ = (CheckConstraint("id = 1", name="ck_briefing_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(80))
    lines: Mapped[list[str]] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_timestamp, onupdate=utc_timestamp)
