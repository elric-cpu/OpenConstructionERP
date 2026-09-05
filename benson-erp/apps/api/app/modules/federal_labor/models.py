import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class FederalComplianceProfile(StrEnum):
    COMMERCIAL = "COMMERCIAL"
    FEDERAL_FIXED_PRICE = "FEDERAL_FIXED_PRICE"
    FEDERAL_COST_REIMBURSEMENT = "FEDERAL_COST_REIMBURSEMENT"
    FEDERAL_TIME_AND_MATERIALS = "FEDERAL_TIME_AND_MATERIALS"
    FEDERAL_LABOR_HOUR = "FEDERAL_LABOR_HOUR"
    FEDERAL_CONSTRUCTION_WAGE_RATE = "FEDERAL_CONSTRUCTION_WAGE_RATE"
    FEDERAL_SERVICE_CONTRACT_LABOR = "FEDERAL_SERVICE_CONTRACT_LABOR"
    STATE_PREVAILING_WAGE = "STATE_PREVAILING_WAGE"
    CUSTOM_COMPLIANCE_PROFILE = "CUSTOM_COMPLIANCE_PROFILE"


class FederalChargeCodeStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EmployeeQualificationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class FederalInvoiceSupportStatus(StrEnum):
    GENERATED = "GENERATED"


class FederalChargeCode(TenantRecord, Base):
    __tablename__ = "federal_charge_codes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        CheckConstraint(
            "active_to IS NULL OR active_to >= active_from",
            name="ck_federal_charge_code_dates",
        ),
        CheckConstraint(
            "(status = 'CLOSED' AND closed_at IS NOT NULL) OR "
            "(status = 'OPEN' AND closed_at IS NULL)",
            name="ck_federal_charge_code_closed_state",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        Index(
            "ix_federal_charge_code_hierarchy",
            "tenant_id",
            "agency_code",
            "contract_code",
            "task_order",
            "clin",
            "funding_line",
        ),
        Index(
            "ix_federal_charge_code_active",
            "tenant_id",
            "status",
            "active_from",
            "active_to",
        ),
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile: Mapped[FederalComplianceProfile] = mapped_column(
        Enum(FederalComplianceProfile),
        nullable=False,
    )
    agency_code: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_code: Mapped[str] = mapped_column(String(100), nullable=False)
    task_order: Mapped[str | None] = mapped_column(String(100))
    delivery_order: Mapped[str | None] = mapped_column(String(100))
    clin: Mapped[str | None] = mapped_column(String(100))
    slin: Mapped[str | None] = mapped_column(String(100))
    funding_line: Mapped[str | None] = mapped_column(String(100))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    cost_code: Mapped[str | None] = mapped_column(String(100))
    labor_category: Mapped[str | None] = mapped_column(String(100))
    active_from: Mapped[date] = mapped_column(Date, nullable=False)
    active_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[FederalChargeCodeStatus] = mapped_column(
        Enum(FederalChargeCodeStatus),
        default=FederalChargeCodeStatus.OPEN,
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    closed_reason: Mapped[str | None] = mapped_column(Text)
    required_qualification_code: Mapped[str | None] = mapped_column(String(100))


class FederalLaborRate(TenantRecord, Base):
    __tablename__ = "federal_labor_rates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "federal_charge_code_id",
            "labor_category",
            "effective_from",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_federal_labor_rate_dates",
        ),
        CheckConstraint(
            "regular_bill_rate >= 0 AND overtime_bill_rate >= 0 "
            "AND double_time_bill_rate >= 0",
            name="ck_federal_labor_rate_nonnegative",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "federal_charge_code_id"],
            ["federal_charge_codes.tenant_id", "federal_charge_codes.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_federal_labor_rate_lookup",
            "tenant_id",
            "federal_charge_code_id",
            "labor_category",
            "effective_from",
        ),
    )

    federal_charge_code_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    labor_category: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    regular_bill_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    overtime_bill_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    double_time_bill_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source_reference: Mapped[str | None] = mapped_column(String(500))


class EmployeeQualification(TenantRecord, Base):
    __tablename__ = "employee_qualifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "employee_id",
            "qualification_code",
            "effective_from",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_employee_qualification_dates",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_employee_qualification_lookup",
            "tenant_id",
            "employee_id",
            "qualification_code",
            "effective_from",
        ),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    qualification_code: Mapped[str] = mapped_column(String(100), nullable=False)
    qualification_name: Mapped[str] = mapped_column(String(200), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[EmployeeQualificationStatus] = mapped_column(
        Enum(EmployeeQualificationStatus),
        default=EmployeeQualificationStatus.ACTIVE,
        nullable=False,
    )
    issuer: Mapped[str | None] = mapped_column(String(200))
    credential_number: Mapped[str | None] = mapped_column(String(200))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class FederalInvoiceSupport(TenantRecord, Base):
    __tablename__ = "federal_invoice_support"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index(
            "uq_federal_invoice_support_scope_version",
            "tenant_id",
            "contract_code",
            text("COALESCE(task_order, '')"),
            "invoice_period_start",
            "invoice_period_end",
            "artifact_version",
            unique=True,
        ),
        CheckConstraint(
            "invoice_period_end >= invoice_period_start",
            name="ck_federal_invoice_support_period",
        ),
        CheckConstraint(
            "total_approved_hours >= 0 AND total_extended_amount >= 0",
            name="ck_federal_invoice_support_totals",
        ),
        Index(
            "ix_federal_invoice_support_contract_period",
            "tenant_id",
            "contract_code",
            "invoice_period_start",
            "invoice_period_end",
        ),
    )

    contract_code: Mapped[str] = mapped_column(String(100), nullable=False)
    task_order: Mapped[str | None] = mapped_column(String(100))
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    invoice_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    artifact_version: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[FederalInvoiceSupportStatus] = mapped_column(
        Enum(FederalInvoiceSupportStatus),
        default=FederalInvoiceSupportStatus.GENERATED,
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    total_approved_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_extended_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class FederalInvoiceSupportLine(TenantRecord, Base):
    __tablename__ = "federal_invoice_support_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "federal_invoice_support_id", "time_entry_id"),
        CheckConstraint(
            "approved_hours >= 0 AND regular_hours >= 0 AND overtime_hours >= 0 "
            "AND double_time_hours >= 0 AND regular_bill_rate >= 0 "
            "AND overtime_bill_rate >= 0 AND double_time_bill_rate >= 0 "
            "AND extended_amount >= 0",
            name="ck_federal_invoice_support_line_amounts",
        ),
        CheckConstraint(
            "approved_hours = regular_hours + overtime_hours + double_time_hours",
            name="ck_federal_invoice_support_line_hours",
        ),
        CheckConstraint(
            "extended_amount = ROUND("
            "regular_hours * regular_bill_rate + "
            "overtime_hours * overtime_bill_rate + "
            "double_time_hours * double_time_bill_rate, 2)",
            name="ck_federal_invoice_support_line_formula",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "federal_invoice_support_id"],
            ["federal_invoice_support.tenant_id", "federal_invoice_support.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "time_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "federal_charge_code_id"],
            ["federal_charge_codes.tenant_id", "federal_charge_codes.id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_federal_invoice_support_line_support",
            "tenant_id",
            "federal_invoice_support_id",
        ),
        Index(
            "ix_federal_invoice_support_line_employee_date",
            "tenant_id",
            "employee_id",
            "work_date",
        ),
    )

    federal_invoice_support_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    time_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_name: Mapped[str] = mapped_column(String(220), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    federal_charge_code_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    agency_code: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_code: Mapped[str] = mapped_column(String(100), nullable=False)
    task_order: Mapped[str | None] = mapped_column(String(100))
    clin: Mapped[str | None] = mapped_column(String(100))
    funding_line: Mapped[str | None] = mapped_column(String(100))
    labor_category: Mapped[str] = mapped_column(String(100), nullable=False)
    approved_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    double_time_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    regular_bill_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    overtime_bill_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    double_time_bill_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    extended_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    qualification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    qualification_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    payroll_reconciliation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    payroll_reconciliation_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    time_approval_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    bill_rate_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
