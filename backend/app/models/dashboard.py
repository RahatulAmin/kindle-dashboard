from datetime import UTC, date, datetime, time

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class Admin(Base):
    __tablename__ = "administrator"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))


class AdminSession(Base):
    __tablename__ = "administrator_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("administrator.id", ondelete="CASCADE"))
    expires_at: Mapped[int] = mapped_column(index=True)


class DashboardSettings(Base):
    __tablename__ = "dashboard_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    preferences: Mapped[dict] = mapped_column(JSON)


class Entry:
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(6))
    completed: Mapped[bool]
    kindle_visible: Mapped[bool]
    created_at: Mapped[str] = mapped_column(String(40), default=utc_timestamp)
    updated_at: Mapped[str] = mapped_column(String(40), default=utc_timestamp, onupdate=utc_timestamp, index=True)
    source: Mapped[str | None] = mapped_column(String(80))
    external_ref: Mapped[str | None] = mapped_column(String(160))


class Task(Entry, Base):
    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint("(source IS NULL) = (external_ref IS NULL)", name="ck_task_external_pair"),
        Index("ix_task_external_identity", "source", "external_ref", unique=True),
        Index("ix_task_external_ref", "external_ref"),
    )

    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    position: Mapped[int]


class Deadline(Entry, Base):
    __tablename__ = "deadline"
    __table_args__ = (
        CheckConstraint("(source IS NULL) = (external_ref IS NULL)", name="ck_deadline_external_pair"),
        Index("ix_deadline_external_identity", "source", "external_ref", unique=True),
        Index("ix_deadline_external_ref", "external_ref"),
    )

    due_date: Mapped[date] = mapped_column(Date, index=True)
    due_time: Mapped[time | None] = mapped_column(Time)
    archived: Mapped[bool]


class PrayerSettings(Base):
    __tablename__ = "prayer_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    preferences: Mapped[dict] = mapped_column(JSON)


class PrayerMonth(Base):
    __tablename__ = "prayer_month"

    calculation: Mapped[str] = mapped_column(String(64), primary_key=True)
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    days: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(String(40))
