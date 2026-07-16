from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

ScheduleEventType = Literal["site_visit", "work", "inspection", "delivery"]
ScheduleStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]

MAX_SCHEDULE_EVENT_DURATION = timedelta(hours=24)
SCHEDULE_TRANSITIONS = {
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Schedule timestamps must include an RFC3339 UTC offset")
    return value


def _zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Timezone must be a valid IANA timezone") from error


def _validate_local_offset(value: datetime, timezone: str) -> None:
    zone = _zone(timezone)
    round_trip = value.astimezone(UTC).astimezone(zone)
    if (
        round_trip.replace(tzinfo=None) != value.replace(tzinfo=None)
        or round_trip.utcoffset() != value.utcoffset()
    ):
        raise ValueError(
            "Timestamp offset does not identify a valid local time in the timezone"
        )


class ScheduleEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    event_type: ScheduleEventType
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(default="America/Los_Angeles", min_length=1, max_length=64)
    assigned_to: EmailStr

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @model_validator(mode="after")
    def interval_is_valid(self) -> "ScheduleEntryCreate":
        _validate_interval(self.starts_at, self.ends_at, self.timezone)
        return self


class ScheduleEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    event_type: ScheduleEventType | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    assigned_to: EmailStr | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value) if value is not None else None

    @field_validator("timezone")
    @classmethod
    def timezone_is_known(cls, value: str | None) -> str | None:
        if value is not None:
            _zone(value)
        return value

    @model_validator(mode="after")
    def explicit_values_cannot_be_null(self) -> "ScheduleEntryUpdate":
        nullable_fields = {"starts_at", "ends_at", "timezone", "assigned_to"}
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in nullable_fields
        ):
            raise ValueError("Schedule update fields cannot be null")
        return self


class ScheduleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["in_progress", "completed", "cancelled"]
    expected_version: int = Field(ge=1)
    note: str = Field(default="", max_length=2_000)


class ScheduleEntrySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_id: UUID
    job_number: str
    job_title: str
    customer_name: str
    site_address: str
    event_type: ScheduleEventType
    status: ScheduleStatus
    starts_at: datetime
    ends_at: datetime
    timezone: str
    assigned_to: EmailStr
    version: int
    created_at: datetime
    updated_at: datetime


class ScheduleStatusHistorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    schedule_entry_id: UUID
    from_status: ScheduleStatus
    to_status: ScheduleStatus
    note: str
    actor: EmailStr
    occurred_at: datetime


def validate_schedule_interval(
    starts_at: datetime, ends_at: datetime, timezone: str
) -> None:
    _validate_interval(starts_at, ends_at, timezone)


def _validate_interval(starts_at: datetime, ends_at: datetime, timezone: str) -> None:
    _validate_local_offset(starts_at, timezone)
    _validate_local_offset(ends_at, timezone)
    if ends_at <= starts_at:
        raise ValueError("Schedule end must be after its start")
    if ends_at - starts_at > MAX_SCHEDULE_EVENT_DURATION:
        raise ValueError("Schedule events cannot exceed 24 hours")
