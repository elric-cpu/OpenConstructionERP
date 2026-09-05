import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.payroll.models import (
    PayrollExportFormat,
    PayrollExportStatus,
    PayrollMappingType,
    PayrollPeriodExportStatus,
    PayrollPeriodStatus,
    PayrollReconciliationStatus,
    PayrollResultImportStatus,
)


class PayrollPeriodCreate(BaseModel):
    period_start: date
    period_end: date
    pay_date: date
    workweek_definition: str = Field(min_length=3, max_length=100)
    provider: str = Field(min_length=2, max_length=80)

    @model_validator(mode="after")
    def validate_dates(self) -> "PayrollPeriodCreate":
        if self.period_end < self.period_start:
            raise ValueError("Payroll period end must not precede its start")
        if (self.period_end - self.period_start).days > 31:
            raise ValueError("Payroll periods cannot exceed 32 calendar days")
        if self.pay_date < self.period_end:
            raise ValueError("Pay date must not precede the period end")
        return self


class PayrollPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    period_start: date
    period_end: date
    pay_date: date
    status: PayrollPeriodStatus
    workweek_definition: str
    provider: str
    approved_by: uuid.UUID | None
    locked_at: datetime | None
    export_status: PayrollPeriodExportStatus
    reconciliation_status: PayrollReconciliationStatus
    review_reason: str | None
    validation_snapshot: dict | None
    version: int


class PayrollPeriodTransition(BaseModel):
    target_status: PayrollPeriodStatus
    reason: str = Field(min_length=5, max_length=2000)


class EmployeePayRateCreate(BaseModel):
    employee_id: uuid.UUID
    effective_from: date
    effective_to: date | None = None
    base_rate: Decimal = Field(gt=0, decimal_places=4)
    overtime_rate: Decimal = Field(gt=0, decimal_places=4)
    double_time_rate: Decimal = Field(gt=0, decimal_places=4)
    fringe_rate: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    cash_in_lieu_rate: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)

    @model_validator(mode="after")
    def validate_dates(self) -> "EmployeePayRateCreate":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Pay-rate end must not precede its start")
        return self


class EmployeePayRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    effective_from: date
    effective_to: date | None
    base_rate: Decimal
    overtime_rate: Decimal
    double_time_rate: Decimal
    fringe_rate: Decimal
    cash_in_lieu_rate: Decimal
    version: int


class PayrollMappingCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=80)
    mapping_type: PayrollMappingType
    internal_key: str = Field(min_length=1, max_length=200)
    external_code: str = Field(min_length=1, max_length=200)
    effective_from: date
    effective_to: date | None = None
    configuration: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> "PayrollMappingCreate":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Mapping end must not precede its start")
        return self


class PayrollMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    mapping_type: PayrollMappingType
    internal_key: str
    external_code: str
    effective_from: date
    effective_to: date | None
    configuration: dict
    version: int


class PayrollPreviewException(BaseModel):
    code: str
    message: str
    time_entry_id: uuid.UUID | None = None
    employee_id: uuid.UUID | None = None
    internal_key: str | None = None


class PayrollPreviewEmployee(BaseModel):
    employee_id: uuid.UUID
    employee_number: str
    employee_name: str
    regular_hours: Decimal
    overtime_hours: Decimal
    double_time_hours: Decimal
    travel_hours: Decimal
    leave_hours: Decimal
    indirect_hours: Decimal
    estimated_gross_labor: Decimal | None
    source_time_entry_ids: list[uuid.UUID]


class PayrollPreview(BaseModel):
    payroll_period_id: uuid.UUID
    provider: str
    approved_entry_count: int
    unapproved_entry_count: int
    employees: list[PayrollPreviewEmployee]
    exceptions: list[PayrollPreviewException]
    totals: dict[str, str | int | None]
    calculation: dict[str, str]
    ready_to_lock: bool


class PayrollExportCreate(BaseModel):
    format: PayrollExportFormat
    include_sensitive_fields: bool = False


class PayrollExportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payroll_period_id: uuid.UUID
    provider: str
    format: PayrollExportFormat
    artifact_version: int
    generated_at: datetime
    generated_by: uuid.UUID
    file_checksum: str
    filename: str
    content_type: str
    status: PayrollExportStatus
    includes_sensitive_fields: bool
    totals_snapshot: dict
    version: int


class PayrollResultLineInput(BaseModel):
    time_entry_id: uuid.UUID
    provider_employee_id: str = Field(min_length=1, max_length=200)
    provider_payroll_id: str | None = Field(default=None, max_length=300)
    payment_reference: str | None = Field(default=None, max_length=300)
    work_date: date
    pay_date: date
    regular_hours: Decimal = Field(ge=0, decimal_places=2)
    overtime_hours: Decimal = Field(ge=0, decimal_places=2)
    double_time_hours: Decimal = Field(ge=0, decimal_places=2)
    travel_hours: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    leave_hours: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    indirect_hours: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    base_rate: Decimal = Field(ge=0, decimal_places=4)
    overtime_rate: Decimal = Field(ge=0, decimal_places=4)
    double_time_rate: Decimal = Field(ge=0, decimal_places=4)
    gross_wages: Decimal = Field(ge=0, decimal_places=2)
    employer_taxes: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    employee_deductions: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    employer_benefits: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    workers_compensation: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    fringe_benefits: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    net_pay: Decimal = Field(ge=0, decimal_places=2)
    is_adjustment: bool = False


class PayrollResultImportCreate(BaseModel):
    payroll_export_id: uuid.UUID
    provider_reference: str = Field(min_length=1, max_length=300)
    lines: list[PayrollResultLineInput] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def unique_time_entries(self) -> "PayrollResultImportCreate":
        ids = [line.time_entry_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Provider result contains duplicate time-entry rows")
        return self


class PayrollReconciliationExceptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payroll_result_line_id: uuid.UUID | None
    code: str
    message: str
    expected_value: str | None
    actual_value: str | None
    status: str
    version: int


class PayrollExceptionResolution(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class PayrollResultImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payroll_period_id: uuid.UUID
    payroll_export_id: uuid.UUID
    provider: str
    provider_reference: str
    source_checksum: str
    imported_at: datetime
    status: PayrollResultImportStatus
    reconciliation_summary: dict | None
    reconciled_at: datetime | None
    version: int


class PayrollReconciliationRead(BaseModel):
    result_import: PayrollResultImportRead
    exceptions: list[PayrollReconciliationExceptionRead]
    job_cost_count: int
    job_cost_total: Decimal
    calculation: dict[str, str]
