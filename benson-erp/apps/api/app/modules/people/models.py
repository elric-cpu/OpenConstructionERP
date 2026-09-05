import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class EmployeeStatus(StrEnum):
    DRAFT = "DRAFT"
    IDENTITY_REQUESTED = "IDENTITY_REQUESTED"
    IDENTITY_CREATED = "IDENTITY_CREATED"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class IdentityProvisioningStatus(StrEnum):
    PENDING = "PENDING"
    CREATED = "CREATED"


class Employee(TenantRecord, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "employee_number"),
        UniqueConstraint("tenant_id", "company_username"),
        UniqueConstraint("tenant_id", "company_email"),
        UniqueConstraint("tenant_id", "user_id"),
    )

    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    personal_email: Mapped[str] = mapped_column(String(320), nullable=False)
    company_username: Mapped[str] = mapped_column(String(80), nullable=False)
    company_email: Mapped[str | None] = mapped_column(String(320))
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(EmployeeStatus), default=EmployeeStatus.DRAFT, nullable=False
    )
    google_subject_id: Mapped[str | None] = mapped_column(String(100))
    google_org_unit_path: Mapped[str | None] = mapped_column(String(500))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    identity_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erp_access_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdentityProvisioningRequest(TenantRecord, Base):
    __tablename__ = "identity_provisioning_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "employee_id"),
        UniqueConstraint("tenant_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="CASCADE",
        ),
        Index("ix_identity_requests_tenant_status", "tenant_id", "status"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[IdentityProvisioningStatus] = mapped_column(
        Enum(IdentityProvisioningStatus),
        default=IdentityProvisioningStatus.PENDING,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_email: Mapped[str] = mapped_column(String(320), nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(100))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmployeeActivationRequest(TenantRecord, Base):
    __tablename__ = "employee_activation_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("token_hash"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="CASCADE",
        ),
        Index(
            "ix_employee_activation_active",
            "tenant_id",
            "employee_id",
            "expires_at",
        ),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_delivery_secret: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
