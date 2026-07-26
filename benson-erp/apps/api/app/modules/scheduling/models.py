import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class ActivityStatus(StrEnum):
    PLANNED = "PLANNED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"


class Schedule(TenantRecord, Base):
    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "project_id"),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)


class ScheduleActivity(TenantRecord, Base):
    __tablename__ = "schedule_activities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint("end_at > start_at", name="ck_schedule_activity_positive_duration"),
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["schedules.tenant_id", "schedules.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
        ),
        Index("ix_schedule_activity_tenant_window", "tenant_id", "start_at", "end_at"),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ActivityStatus] = mapped_column(
        Enum(ActivityStatus), default=ActivityStatus.PLANNED, nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(500))
    required_tools: Mapped[str | None] = mapped_column(Text)


class ScheduleAssignment(TenantRecord, Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "activity_id", "employee_id"),
        ForeignKeyConstraint(
            ["tenant_id", "activity_id"],
            ["schedule_activities.tenant_id", "schedule_activities.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="CASCADE",
        ),
        Index("ix_schedule_assignment_tenant_employee", "tenant_id", "employee_id"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    assignment_role: Mapped[str | None] = mapped_column(String(100))
