import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.scheduling.models import ActivityStatus


class ScheduleCreate(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="America/Los_Angeles", min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Schedule timezone must be a valid IANA timezone") from exc
        return value


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    timezone: str
    version: int


class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    start_at: datetime
    end_at: datetime
    location: str | None = Field(default=None, max_length=500)
    required_tools: str | None = Field(default=None, max_length=5000)

    @field_validator("start_at", "end_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Schedule timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "ActivityCreate":
        if self.end_at <= self.start_at:
            raise ValueError("Activity end must be after its start")
        return self


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    schedule_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    status: ActivityStatus
    location: str | None
    required_tools: str | None
    version: int


class AssignmentCreate(BaseModel):
    employee_id: uuid.UUID
    assignment_role: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=3, max_length=1000)


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_id: uuid.UUID
    employee_id: uuid.UUID
    assignment_role: str | None
    version: int


class ScheduleEntryRead(BaseModel):
    activity: ActivityRead
    assignment: AssignmentRead | None
    employee_name: str | None
    project_name: str
