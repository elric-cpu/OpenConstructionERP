import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class PayrollPeriodStatus(StrEnum):
    OPEN = "OPEN"
    EMPLOYEE_REVIEW = "EMPLOYEE_REVIEW"
    SUPERVISOR_REVIEW = "SUPERVISOR_REVIEW"
    PAYROLL_REVIEW = "PAYROLL_REVIEW"
    LOCKED = "LOCKED"
    EXPORTED = "EXPORTED"
    PROCESSED = "PROCESSED"
    RECONCILED = "RECONCILED"


class PayrollPeriodExportStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    GENERATED = "GENERATED"
    PROCESSED = "PROCESSED"


class PayrollReconciliationStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    EXCEPTIONS = "EXCEPTIONS"
    RECONCILED = "RECONCILED"


class PayrollMappingType(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    EARNING = "EARNING"
    DEDUCTION = "DEDUCTION"
    PROJECT = "PROJECT"
    COST_CODE = "COST_CODE"
    DEPARTMENT = "DEPARTMENT"
    LABOR_CATEGORY = "LABOR_CATEGORY"
    LEAVE = "LEAVE"


class PayrollExportFormat(StrEnum):
    CSV = "CSV"
    XLSX = "XLSX"
    JSON = "JSON"


class PayrollExportStatus(StrEnum):
    GENERATED = "GENERATED"
    TRANSMITTED = "TRANSMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"


class PayrollResultImportStatus(StrEnum):
    IMPORTED = "IMPORTED"
    EXCEPTIONS = "EXCEPTIONS"
    RECONCILED = "RECONCILED"


class ReconciliationExceptionStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class PayrollPeriod(TenantRecord, Base):
    __tablename__ = "payroll_periods"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "period_start", "period_end"),
        Index("ix_payroll_period_tenant_status", "tenant_id", "status"),
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PayrollPeriodStatus] = mapped_column(
        Enum(PayrollPeriodStatus),
        default=PayrollPeriodStatus.OPEN,
        nullable=False,
    )
    workweek_definition: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_status: Mapped[PayrollPeriodExportStatus] = mapped_column(
        Enum(PayrollPeriodExportStatus),
        default=PayrollPeriodExportStatus.NOT_STARTED,
        nullable=False,
    )
    reconciliation_status: Mapped[PayrollReconciliationStatus] = mapped_column(
        Enum(PayrollReconciliationStatus),
        default=PayrollReconciliationStatus.NOT_STARTED,
        nullable=False,
    )
    review_reason: Mapped[str | None] = mapped_column(Text)
    validation_snapshot: Mapped[dict | None] = mapped_column(JSON)


class EmployeePayRate(TenantRecord, Base):
    __tablename__ = "employee_pay_rates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "employee_id", "effective_from"),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        Index("ix_pay_rate_tenant_employee_dates", "tenant_id", "employee_id", "effective_from"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    base_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    overtime_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    double_time_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    fringe_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    cash_in_lieu_rate: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=0
    )


class PayrollProviderMapping(TenantRecord, Base):
    __tablename__ = "payroll_provider_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "mapping_type",
            "internal_key",
            "effective_from",
        ),
        Index(
            "ix_payroll_mapping_lookup",
            "tenant_id",
            "provider",
            "mapping_type",
            "internal_key",
        ),
    )

    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    mapping_type: Mapped[PayrollMappingType] = mapped_column(
        Enum(PayrollMappingType),
        nullable=False,
    )
    internal_key: Mapped[str] = mapped_column(String(200), nullable=False)
    external_code: Mapped[str] = mapped_column(String(200), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class PayrollExport(TenantRecord, Base):
    __tablename__ = "payroll_exports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "payroll_period_id",
            "provider",
            "format",
            "artifact_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_period_id"],
            ["payroll_periods.tenant_id", "payroll_periods.id"],
        ),
        Index("ix_payroll_export_tenant_period", "tenant_id", "payroll_period_id"),
    )

    payroll_period_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    format: Mapped[PayrollExportFormat] = mapped_column(
        Enum(PayrollExportFormat),
        nullable=False,
    )
    artifact_version: Mapped[int] = mapped_column(nullable=False, default=1)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[PayrollExportStatus] = mapped_column(
        Enum(PayrollExportStatus),
        default=PayrollExportStatus.GENERATED,
        nullable=False,
    )
    includes_sensitive_fields: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    totals_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(300))
    transmitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class PayrollExportLine(TenantRecord, Base):
    __tablename__ = "payroll_export_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "payroll_export_id", "time_entry_id"),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_export_id"],
            ["payroll_exports.tenant_id", "payroll_exports.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "time_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        Index("ix_payroll_export_line_tenant_export", "tenant_id", "payroll_export_id"),
    )

    payroll_export_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    time_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(220), nullable=False)
    provider_employee_id: Mapped[str] = mapped_column(String(200), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    double_time_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    travel_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    leave_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    indirect_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    project_code: Mapped[str | None] = mapped_column(String(200))
    cost_code: Mapped[str | None] = mapped_column(String(200))
    charge_code: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_code: Mapped[str | None] = mapped_column(String(100))
    task_order: Mapped[str | None] = mapped_column(String(100))
    clin: Mapped[str | None] = mapped_column(String(100))
    funding_line: Mapped[str | None] = mapped_column(String(100))
    labor_category: Mapped[str | None] = mapped_column(String(100))
    work_classification: Mapped[str | None] = mapped_column(String(150))
    wage_determination: Mapped[str | None] = mapped_column(String(150))
    base_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    overtime_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    double_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    fringe_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    cash_in_lieu_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    gross_labor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    job_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    mapping_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class PayrollResultImport(TenantRecord, Base):
    __tablename__ = "payroll_result_imports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "payroll_export_id"),
        UniqueConstraint("tenant_id", "provider", "provider_reference"),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_period_id"],
            ["payroll_periods.tenant_id", "payroll_periods.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_export_id"],
            ["payroll_exports.tenant_id", "payroll_exports.id"],
        ),
        Index("ix_payroll_result_import_period", "tenant_id", "payroll_period_id"),
    )

    payroll_period_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payroll_export_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[PayrollResultImportStatus] = mapped_column(
        Enum(PayrollResultImportStatus),
        default=PayrollResultImportStatus.IMPORTED,
        nullable=False,
    )
    reconciliation_summary: Mapped[dict | None] = mapped_column(JSON)
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class PayrollResultLine(TenantRecord, Base):
    __tablename__ = "payroll_result_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "payroll_result_import_id", "time_entry_id"),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_result_import_id"],
            ["payroll_result_imports.tenant_id", "payroll_result_imports.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_export_line_id"],
            ["payroll_export_lines.tenant_id", "payroll_export_lines.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "time_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        Index("ix_payroll_result_line_import", "tenant_id", "payroll_result_import_id"),
    )

    payroll_result_import_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payroll_export_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    time_entry_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    provider_employee_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_payroll_id: Mapped[str | None] = mapped_column(String(300))
    payment_reference: Mapped[str | None] = mapped_column(String(300))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    regular_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    double_time_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    travel_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    leave_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    indirect_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    base_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    overtime_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    double_time_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    gross_wages: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    employer_taxes: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    employee_deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    employer_benefits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    workers_compensation: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fringe_benefits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_adjustment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PayrollReconciliationException(TenantRecord, Base):
    __tablename__ = "payroll_reconciliation_exceptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_result_import_id"],
            ["payroll_result_imports.tenant_id", "payroll_result_imports.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_result_line_id"],
            ["payroll_result_lines.tenant_id", "payroll_result_lines.id"],
        ),
        Index(
            "ix_payroll_reconciliation_exception_import",
            "tenant_id",
            "payroll_result_import_id",
            "status",
        ),
    )

    payroll_result_import_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    payroll_result_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(String(300))
    actual_value: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[ReconciliationExceptionStatus] = mapped_column(
        Enum(ReconciliationExceptionStatus),
        default=ReconciliationExceptionStatus.OPEN,
        nullable=False,
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class PayrollJobCost(TenantRecord, Base):
    __tablename__ = "payroll_job_costs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "payroll_result_line_id"),
        ForeignKeyConstraint(
            ["tenant_id", "payroll_result_line_id"],
            ["payroll_result_lines.tenant_id", "payroll_result_lines.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        Index("ix_payroll_job_cost_project", "tenant_id", "project_id", "cost_code"),
    )

    payroll_result_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    cost_code: Mapped[str | None] = mapped_column(String(200))
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    direct_wages: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    employer_taxes: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    employer_benefits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    workers_compensation: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fringe_benefits: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    calculation_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
