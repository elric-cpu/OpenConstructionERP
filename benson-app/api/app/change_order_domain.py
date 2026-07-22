from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ChangeOrderStatus = Literal["draft", "submitted", "approved", "rejected", "void"]


class ChangeOrderLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=1_000)
    quantity: Decimal = Field(gt=0, le=1_000_000, max_digits=12, decimal_places=2)
    unit: str = Field(default="each", min_length=1, max_length=40)
    unit_price_cents: int = Field(ge=0, le=100_000_000)

    def total_cents(self) -> int:
        return int(
            (self.quantity * self.unit_price_cents).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )


class ChangeOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    originating_field_report_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    schedule_impact_days: int = Field(default=0, ge=-365, le=3_650)
    internal_notes: str = Field(default="", max_length=10_000)
    customer_explanation: str = Field(min_length=1, max_length=20_000)
    lines: list[ChangeOrderLineInput] = Field(min_length=1, max_length=200)


class ChangeOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    schedule_impact_days: int | None = Field(default=None, ge=-365, le=3_650)
    internal_notes: str | None = Field(default=None, max_length=10_000)
    customer_explanation: str | None = Field(
        default=None, min_length=1, max_length=20_000
    )
    lines: list[ChangeOrderLineInput] | None = Field(
        default=None, min_length=1, max_length=200
    )


class ChangeOrderTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: Literal["submitted", "approved", "rejected", "void"]
    note: str = Field(default="", max_length=5_000)


class ChangeOrderRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=5_000)


class ChangeOrderLineSummary(ChangeOrderLineInput):
    id: UUID
    position: int
    line_total_cents: int


class ChangeOrderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    root_id: UUID
    previous_revision_id: UUID | None
    revision: int
    number: str
    job_id: UUID
    job_number: str
    job_title: str
    estimate_id: UUID
    customer_id: UUID
    customer_name: str
    originating_field_report_id: UUID | None
    status: ChangeOrderStatus
    version: int
    title: str
    schedule_impact_days: int
    internal_notes: str
    customer_explanation: str
    subtotal_cents: int
    lines: list[ChangeOrderLineSummary]
    created_by: EmailStr
    submitted_by: EmailStr | None
    submitted_at: datetime | None
    decided_by: EmailStr | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime


class ChangeOrderEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    change_order_id: UUID
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: EmailStr
    created_at: datetime
