import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class TimeEntryStatus(StrEnum):
    DRAFT = "DRAFT"
    CERTIFIED = "CERTIFIED"
    APPROVED = "APPROVED"
    CORRECTED = "CORRECTED"


class TimeEntrySource(StrEnum):
    WEB = "WEB"
    OFFLINE = "OFFLINE"
    CREW = "CREW"


class TimeCorrectionStatus(StrEnum):
    PENDING_RECERTIFICATION = "PENDING_RECERTIFICATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    COMPLETED = "COMPLETED"


class TimeEntry(TenantRecord, Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "client_operation_id"),
        CheckConstraint("end_at > start_at", name="ck_time_entry_positive_duration"),
        CheckConstraint("break_minutes >= 0", name="ck_time_entry_break_nonnegative"),
        CheckConstraint("total_hours >= 0", name="ck_time_entry_total_nonnegative"),
        CheckConstraint(
            "total_hours = regular_hours + overtime_hours + double_time_hours"
            " + travel_hours + leave_hours + indirect_hours",
            name="ck_time_entry_classified_total",
        ),
        CheckConstraint(
            "uncompensated_overtime_hours <= overtime_hours",
            name="ck_time_entry_uncompensated_subset",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "schedule_assignment_id"],
            ["schedule_assignments.tenant_id", "schedule_assignments.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "federal_charge_code_id"],
            ["federal_charge_codes.tenant_id", "federal_charge_codes.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_time_entry_tenant_employee_date", "tenant_id", "employee_id", "work_date"),
        Index("ix_time_entry_tenant_status", "tenant_id", "status"),
        Index(
            "ix_time_entry_tenant_federal_charge_code",
            "tenant_id",
            "federal_charge_code_id",
        ),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    break_minutes: Mapped[int] = mapped_column(nullable=False, default=0)
    total_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    double_time_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    travel_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    leave_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    indirect_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    uncompensated_overtime_hours: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=0
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    schedule_assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    federal_charge_code_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    contract_code: Mapped[str | None] = mapped_column(String(100))
    task_order: Mapped[str | None] = mapped_column(String(100))
    clin: Mapped[str | None] = mapped_column(String(100))
    funding_line: Mapped[str | None] = mapped_column(String(100))
    charge_code: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_code: Mapped[str | None] = mapped_column(String(100))
    labor_category: Mapped[str | None] = mapped_column(String(100))
    work_classification: Mapped[str | None] = mapped_column(String(150))
    wage_determination: Mapped[str | None] = mapped_column(String(150))
    trade: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    late_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TimeEntryStatus] = mapped_column(
        Enum(TimeEntryStatus), default=TimeEntryStatus.DRAFT, nullable=False
    )
    source: Mapped[TimeEntrySource] = mapped_column(Enum(TimeEntrySource), nullable=False)
    client_operation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(200))
    original_device_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    server_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    certified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    certification_statement: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class TimeCorrection(TenantRecord, Base):
    __tablename__ = "time_corrections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "original_entry_id"),
        UniqueConstraint("tenant_id", "replacement_entry_id"),
        ForeignKeyConstraint(
            ["tenant_id", "original_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "replacement_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        Index("ix_time_correction_tenant_status", "tenant_id", "status"),
    )

    original_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    replacement_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[TimeCorrectionStatus] = mapped_column(
        Enum(TimeCorrectionStatus),
        default=TimeCorrectionStatus.PENDING_RECERTIFICATION,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
