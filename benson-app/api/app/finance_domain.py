from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvoiceKind(StrEnum):
    DEPOSIT = "deposit"
    PROGRESS = "progress"
    FINAL = "final"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    VOID = "void"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SETTLED = "settled"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


InvoiceLineSource = Literal["estimate", "change_order"]


class InvoiceLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=1_000)
    quantity: Decimal = Field(gt=0, le=1_000_000, max_digits=12, decimal_places=2)
    unit: str = Field(default="each", min_length=1, max_length=40)
    unit_price_cents: int = Field(ge=0, le=100_000_000)
    source_type: InvoiceLineSource
    source_id: UUID

    def total_cents(self) -> int:
        return int(
            (self.quantity * self.unit_price_cents).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    kind: InvoiceKind
    issue_date: date
    due_date: date
    memo: str = Field(default="", max_length=10_000)
    tax_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    retainage_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    retainage_release_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    lines: list[InvoiceLineInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_dates_and_retainage(self) -> "InvoiceCreate":
        if self.due_date < self.issue_date:
            raise ValueError("Invoice due date cannot precede its issue date")
        subtotal = sum(line.total_cents() for line in self.lines)
        if self.retainage_cents > subtotal:
            raise ValueError("Retainage cannot exceed the current gross billing")
        if self.kind == InvoiceKind.DEPOSIT and self.retainage_cents:
            raise ValueError("Deposit invoices cannot withhold retainage")
        return self


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    due_date: date | None = None
    memo: str | None = Field(default=None, max_length=10_000)
    tax_cents: int | None = Field(default=None, ge=0, le=100_000_000_000)
    retainage_cents: int | None = Field(default=None, ge=0, le=100_000_000_000)
    retainage_release_cents: int | None = Field(default=None, ge=0, le=100_000_000_000)
    lines: list[InvoiceLineInput] | None = Field(
        default=None, min_length=1, max_length=500
    )


class InvoiceTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: Literal["approved", "void"]
    note: str = Field(default="", max_length=5_000)


class CreditCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    amount_cents: int = Field(gt=0, le=100_000_000_000)
    reason: str = Field(min_length=1, max_length=5_000)


class CheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=16, max_length=200)
    success_url: str = Field(min_length=1, max_length=2_000)
    cancel_url: str = Field(min_length=1, max_length=2_000)


class InvoiceLineSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    position: int
    description: str
    quantity: Decimal
    unit: str
    unit_price_cents: int
    line_total_cents: int
    source_type: InvoiceLineSource
    source_id: UUID


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    number: str
    job_id: UUID
    customer_id: UUID
    kind: InvoiceKind
    status: InvoiceStatus
    version: int
    issue_date: date
    due_date: date
    currency: Literal["USD"]
    memo: str
    subtotal_cents: int
    tax_cents: int
    retainage_cents: int
    retainage_release_cents: int
    total_cents: int
    open_balance_cents: int
    snapshot_sha256: str | None
    lines: list[InvoiceLineSummary]
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    voided_by: str | None
    voided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JournalLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_code: str = Field(min_length=1, max_length=40)
    debit_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    credit_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    job_id: UUID | None = None
    customer_id: UUID | None = None
    invoice_id: UUID | None = None

    @model_validator(mode="after")
    def require_one_side(self) -> "JournalLineInput":
        if (self.debit_cents == 0) == (self.credit_cents == 0):
            raise ValueError("Journal line must have exactly one non-zero side")
        return self


class JournalEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=16, max_length=200)
    source_type: str = Field(min_length=1, max_length=60)
    source_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    occurred_at: datetime
    lines: list[JournalLineInput] = Field(min_length=2, max_length=200)

    @model_validator(mode="after")
    def require_balance(self) -> "JournalEntryCreate":
        debits = sum(line.debit_cents for line in self.lines)
        credits = sum(line.credit_cents for line in self.lines)
        if debits != credits:
            raise ValueError("Journal entry debits and credits must balance")
        return self
