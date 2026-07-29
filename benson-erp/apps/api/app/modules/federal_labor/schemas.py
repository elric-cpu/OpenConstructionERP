import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.federal_labor.models import (
    EmployeeQualificationStatus,
    FederalChargeCodeStatus,
    FederalComplianceProfile,
    FederalInvoiceSupportStatus,
)


class DateEffectiveSchema(BaseModel):
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_effective_dates(self) -> "DateEffectiveSchema":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("Effective-to date cannot precede effective-from date")
        return self


class FederalChargeCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    profile: FederalComplianceProfile
    agency_code: str = Field(min_length=1, max_length=100)
    contract_code: str = Field(min_length=1, max_length=100)
    task_order: str | None = Field(default=None, max_length=100)
    delivery_order: str | None = Field(default=None, max_length=100)
    clin: str | None = Field(default=None, max_length=100)
    slin: str | None = Field(default=None, max_length=100)
    funding_line: str | None = Field(default=None, max_length=100)
    project_id: uuid.UUID | None = None
    cost_code: str | None = Field(default=None, max_length=100)
    labor_category: str | None = Field(default=None, max_length=100)
    active_from: date
    active_to: date | None = None
    required_qualification_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_active_dates(self) -> "FederalChargeCodeCreate":
        if self.active_to is not None and self.active_to < self.active_from:
            raise ValueError("Active-to date cannot precede active-from date")
        return self


class FederalChargeCodeRead(FederalChargeCodeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: FederalChargeCodeStatus
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    closed_reason: str | None
    version: int


class FederalChargeCodeClose(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class FederalLaborRateCreate(DateEffectiveSchema):
    federal_charge_code_id: uuid.UUID
    labor_category: str = Field(min_length=1, max_length=100)
    regular_bill_rate: Decimal = Field(ge=0, decimal_places=4)
    overtime_bill_rate: Decimal = Field(ge=0, decimal_places=4)
    double_time_bill_rate: Decimal = Field(ge=0, decimal_places=4)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    source_reference: str | None = Field(default=None, max_length=500)


class FederalLaborRateRead(FederalLaborRateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int


class EmployeeQualificationCreate(DateEffectiveSchema):
    employee_id: uuid.UUID
    qualification_code: str = Field(min_length=1, max_length=100)
    qualification_name: str = Field(min_length=1, max_length=200)
    status: EmployeeQualificationStatus = EmployeeQualificationStatus.ACTIVE
    issuer: str | None = Field(default=None, max_length=200)
    credential_number: str | None = Field(default=None, max_length=200)
    evidence_document_id: uuid.UUID | None = None


class EmployeeQualificationRead(EmployeeQualificationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    verified_at: datetime | None
    verified_by: uuid.UUID | None
    version: int


class FederalInvoiceSupportRequest(BaseModel):
    contract_code: str = Field(min_length=1, max_length=100)
    task_order: str | None = Field(default=None, max_length=100)
    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_period_start: date
    invoice_period_end: date

    @model_validator(mode="after")
    def validate_invoice_period(self) -> "FederalInvoiceSupportRequest":
        if self.invoice_period_end < self.invoice_period_start:
            raise ValueError("Invoice-period end cannot precede its start")
        return self


class FederalInvoiceSupportLinePreview(BaseModel):
    time_entry_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    work_date: date
    federal_charge_code_id: uuid.UUID
    agency_code: str
    contract_code: str
    task_order: str | None
    clin: str | None
    funding_line: str | None
    labor_category: str
    approved_hours: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    double_time_hours: Decimal
    regular_bill_rate: Decimal
    overtime_bill_rate: Decimal
    double_time_bill_rate: Decimal
    extended_amount: Decimal
    qualification_status: str
    qualification_snapshot: dict
    payroll_reconciliation_status: str
    payroll_reconciliation_snapshot: dict
    time_approval_snapshot: dict
    bill_rate_snapshot: dict


class FederalInvoiceSupportLineRead(FederalInvoiceSupportLinePreview):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class FederalInvoiceException(BaseModel):
    code: str
    message: str
    time_entry_id: uuid.UUID | None = None
    blocking: bool = True


class FederalInvoicePreview(BaseModel):
    lines: list[FederalInvoiceSupportLinePreview]
    total_approved_hours: Decimal
    total_extended_amount: Decimal
    exceptions: list[FederalInvoiceException]
    ready: bool


class FederalInvoiceSupportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_code: str
    task_order: str | None
    invoice_number: str | None
    invoice_period_start: date
    invoice_period_end: date
    artifact_version: int
    status: FederalInvoiceSupportStatus
    generated_at: datetime
    generated_by: uuid.UUID
    total_approved_hours: Decimal
    total_extended_amount: Decimal
    source_snapshot: dict
    content_checksum: str
    version: int
    lines: list[FederalInvoiceSupportLineRead] = Field(default_factory=list)


class FloorCheckEntry(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    work_date: date
    location: str | None
    description: str
    contract_code: str
    task_order: str | None
    clin: str | None
    labor_category: str
    approved_hours: Decimal
    time_entry_status: str
    certified_at: datetime | None
    approved_at: datetime | None
    approved_by: uuid.UUID | None
    payroll_status: str
    invoice_status: str


class FloorCheckReport(BaseModel):
    period_start: date
    period_end: date
    entries: list[FloorCheckEntry]
