from datetime import date, time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Priority = Literal["low", "normal", "high"]
WidgetName = Literal["datetime", "weather", "tasks", "deadlines", "pomodoro", "nas"]
WIDGETS = ("datetime", "weather", "tasks", "deadlines", "pomodoro", "nas")


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntryInput(InputModel):
    title: Name
    description: str = Field(default="", max_length=4000)
    priority: Priority = "normal"
    completed: bool = False
    kindle_visible: bool = True


class TaskInput(EntryInput):
    due_date: date | None = None
    position: int = Field(default=0, ge=0, le=999999)


class DeadlineInput(EntryInput):
    due_date: date
    due_time: time | None = None
    archived: bool = False

    @field_validator("due_time")
    @classmethod
    def local_time_only(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("Enter a local Toronto time without a timezone")
        return value


class TaskOutput(TaskInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: str
    updated_at: str


class DeadlineOutput(DeadlineInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: str
    updated_at: str
    days_until: int


class Widget(InputModel):
    key: WidgetName
    visible: bool
    limit: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def singleton_limit(self):
        if self.key in {"datetime", "weather"} and self.limit != 1:
            raise ValueError("Date/time and weather each display one item")
        return self


class WeatherLocation(InputModel):
    name: Name = "Montréal, Québec, Canada"
    latitude: float = Field(default=45.5019, ge=-90, le=90)
    longitude: float = Field(default=-73.5674, ge=-180, le=180)
    timezone: str = Field(default="America/Toronto", max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Enter a valid IANA timezone") from exc
        return value


class Preferences(InputModel):
    kindle_data_enabled: bool = False
    dashboard_title: Name = "Kindle Dashboard"
    kindle_refresh_seconds: int = Field(default=30, ge=30, le=3600)
    weather: WeatherLocation = Field(default_factory=WeatherLocation)
    widgets: list[Widget] = Field(default_factory=lambda: [
        Widget(key="datetime", visible=True, limit=1),
        Widget(key="weather", visible=True, limit=1),
        Widget(key="tasks", visible=True, limit=4),
        Widget(key="deadlines", visible=True, limit=4),
        Widget(key="pomodoro", visible=False, limit=1),
        Widget(key="nas", visible=False, limit=1),
    ])

    @field_validator("widgets")
    @classmethod
    def all_widgets_once(cls, values: list[Widget]) -> list[Widget]:
        if len(values) != len(WIDGETS) or {widget.key for widget in values} != set(WIDGETS):
            raise ValueError("Provide each widget exactly once")
        return values
