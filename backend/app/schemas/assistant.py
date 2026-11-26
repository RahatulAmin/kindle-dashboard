from datetime import date
from typing import Annotated, Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.dashboard import DeadlineInput, InputModel, Name, TaskInput

T = TypeVar("T")
Source = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
ExternalRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class Data(BaseModel, Generic[T]):
    data: T


class ExternalIdentity(InputModel):
    source: Source | None = None
    external_ref: ExternalRef | None = None
    expected_updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def external_pair(self):
        pair = {"source", "external_ref"}
        if (self.model_fields_set & pair not in (set(), pair)
                or (self.source is None) != (self.external_ref is None)):
            raise ValueError("Supply source and external_ref together.")
        return self


class TaskChange(TaskInput, ExternalIdentity):
    title: Name | None = None


class DeadlineChange(DeadlineInput, ExternalIdentity):
    title: Name | None = None
    due_date: date | None = None


class EntryFilters(InputModel):
    completed: bool | None = None
    due_from: date | None = None
    due_to: date | None = None
    source: Source | None = None
    external_ref: ExternalRef | None = None
    updated_since: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.due_from and self.due_to and self.due_from > self.due_to:
            raise ValueError("due_from must be on or before due_to.")
        return self


BriefingTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
BriefingLine = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class BriefingInput(InputModel):
    title: BriefingTitle
    lines: list[BriefingLine] = Field(max_length=6)

    @field_validator("title", "lines", mode="before")
    @classmethod
    def plain_text(cls, value):
        values = value if isinstance(value, list) else [value]
        if any(isinstance(item, str) and not item.isprintable() for item in values):
            raise ValueError("Use printable single-line text.")
        return value


class BriefingOutput(BriefingInput):
    model_config = ConfigDict(from_attributes=True)
    updated_at: str


class AuditOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    token_id: int
    token_name: str
    action: str
    resource_type: str
    resource_id: int
    timestamp: str
    changed_fields: list[str]
