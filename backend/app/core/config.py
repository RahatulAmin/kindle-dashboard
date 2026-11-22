from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORAGE = ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8765, ge=1, le=65535)
    persistent_data_dir: Path = DEFAULT_STORAGE / "data"
    database_path: Path | None = None
    log_dir: Path = DEFAULT_STORAGE / "logs"
    log_destination: Literal["stdout", "file"] = "stdout"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    app_timezone: str = "America/Toronto"
    temperature_unit: Literal["C", "F"] = "C"
    app_language: str = "en"
    kindle_width: int = Field(default=758, ge=320, le=4096)
    kindle_height: int = Field(default=1024, ge=320, le=4096)
    dashboard_refresh_seconds: PositiveInt = 60
    pomodoro_refresh_seconds: PositiveInt = 30
    photo_rotation_seconds: PositiveInt = 600
    idle_timeout_seconds: PositiveInt = 300

    admin_cookie_secure: bool = True
    admin_session_ttl_seconds: PositiveInt = 28800
    device_token_ttl_seconds: PositiveInt = 2592000

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, name: str) -> str:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Expected an IANA timezone") from exc
        return name

    @property
    def sqlite_path(self) -> Path:
        return (self.database_path or self.persistent_data_dir / "db/dashboard.sqlite3").resolve()
