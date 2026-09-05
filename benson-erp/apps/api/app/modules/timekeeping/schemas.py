import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.timekeeping.models import (
    TimeCorrectionStatus,
    TimeEntrySource,
    TimeEntryStatus,
)

ZERO = Decimal("0.00")


class TimeEntryEmployeeOption(BaseModel):
    id: uuid.UUID
    employee_number: str
    first_name: str
    last_name: str
    is_self: bool


class TimeEntryCreate(BaseModel):
    employee_id: uuid.UUID | None = None
    work_date: date
    start_at: datetime
    end_at: datetime
    break_minutes: int = Field(default=0, ge=0, le=1440)
    regular_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    overtime_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    double_time_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    travel_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    leave_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    indirect_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    uncompensated_overtime_hours: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    project_id: uuid.UUID | None = None
    schedule_assignment_id: uuid.UUID | None = None
    federal_charge_code_id: uuid.UUID | None = None
    contract_code: str | None = Field(default=None, max_length=100)
    task_order: str | None = Field(default=None, max_length=100)
    clin: str | None = Field(default=None, max_length=100)
    funding_line: str | None = Field(default=None, max_length=100)
    charge_code: str = Field(min_length=1, max_length=100)
    cost_code: str | None = Field(default=None, max_length=100)
    labor_category: str | None = Field(default=None, max_length=100)
    work_classification: str | None = Field(default=None, max_length=150)
    wage_determination: str | None = Field(default=None, max_length=150)
    trade: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=3, max_length=5000)
    late_reason: str | None = Field(default=None, max_length=2000)
    source: TimeEntrySource
    client_operation_id: uuid.UUID
    device_id: str | None = Field(default=None, max_length=200)
    original_device_timestamp: datetime

    @field_validator("start_at", "end_at", "original_device_timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timekeeping timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "TimeEntryCreate":
        if self.end_at <= self.start_at:
            raise ValueError("Time entry end must be after its start")
        if self.work_date != self.start_at.date():
            raise ValueError("Work date must match the local start date")
        if self.uncompensated_overtime_hours > self.overtime_hours:
            raise ValueError("Uncompensated overtime cannot exceed overtime hours")
        return self


class TimeEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    work_date: date
    start_at: datetime
    end_at: datetime
    break_minutes: int
    total_hours: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    double_time_hours: Decimal
    travel_hours: Decimal
    leave_hours: Decimal
    indirect_hours: Decimal
    uncompensated_overtime_hours: Decimal
    project_id: uuid.UUID | None
    schedule_assignment_id: uuid.UUID | None
    federal_charge_code_id: uuid.UUID | None
    contract_code: str | None
    task_order: str | None
    clin: str | None
    funding_line: str | None
    charge_code: str
    cost_code: str | None
    labor_category: str | None
    work_classification: str | None
    wage_determination: str | None
    trade: str | None
    location: str | None
    description: str
    late_reason: str | None
    status: TimeEntryStatus
    source: TimeEntrySource
    client_operation_id: uuid.UUID
    original_device_timestamp: datetime
    server_received_at: datetime
    certified_at: datetime | None
    approved_at: datetime | None
    version: int


class TimeCertification(BaseModel):
    statement: str = Field(min_length=10, max_length=2000)


class TimeApproval(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class TimeCorrectionCreate(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    replacement: TimeEntryCreate


class TimeCorrectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_entry_id: uuid.UUID
    replacement_entry_id: uuid.UUID
    reason: str
    requested_by: uuid.UUID
    requested_at: datetime
    status: TimeCorrectionStatus
    completed_at: datetime | None
    version: int
    replacement: TimeEntryRead
