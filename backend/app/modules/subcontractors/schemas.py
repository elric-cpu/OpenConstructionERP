"""‌⁠‍Pydantic schemas for the subcontractors module."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Subcontractor ────────────────────────────────────────────────────────


class SubcontractorBase(BaseModel):
    """‌⁠‍Shared subcontractor fields."""

    model_config = ConfigDict(str_strip_whitespace=True)

    legal_name: str = Field(..., min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=64)
    trade_categories: list[str] = Field(default_factory=list)
    country: str | None = Field(default=None, max_length=2)
    address: dict[str, Any] | None = None
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    contact_id: UUID | None = None


class SubcontractorCreate(SubcontractorBase):
    """‌⁠‍Create payload for Subcontractor."""

    prequalification_status: str = Field(
        default="pending",
        pattern=r"^(pending|approved|suspended|rejected)$",
    )


class SubcontractorUpdate(BaseModel):
    """Partial update for Subcontractor."""

    model_config = ConfigDict(str_strip_whitespace=True)

    legal_name: str | None = Field(default=None, min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, max_length=64)
    trade_categories: list[str] | None = None
    prequalification_status: str | None = Field(
        default=None,
        pattern=r"^(pending|approved|suspended|rejected)$",
    )
    rating_score: Decimal | None = Field(default=None, ge=0, le=100)
    country: str | None = Field(default=None, max_length=2)
    address: dict[str, Any] | None = None
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = None
    is_active: bool | None = None
    contact_id: UUID | None = None


class SubcontractorResponse(BaseModel):
    """Subcontractor returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    contact_id: UUID | None = None
    legal_name: str
    trade_name: str | None = None
    tax_id: str | None = None
    trade_categories: list[str] = Field(default_factory=list)
    prequalification_status: str = "pending"
    rating_score: Decimal = Decimal("0")
    country: str | None = None
    address: dict[str, Any] | None = None
    website: str | None = None
    notes: str | None = None
    is_active: bool = True
    # ── Wave 4 / T12: BuildingConnected-style prequal + insurance tracking ──
    prequal_score: int | None = None
    insurance_expiry_date: date | None = None
    insurance_doc_id: UUID | None = None
    prequal_questionnaire: dict[str, Any] | None = None
    prequal_completed_at: datetime | None = None
    blocked_reason: str | None = None
    is_blocked: bool = False
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class PrequalRequest(BaseModel):
    """Submit a prequalification questionnaire for a subcontractor.

    ``questionnaire`` carries the raw Yes/No / multi-choice answers as a
    plain ``dict[str, Any]`` — the questionnaire shape is intentionally
    loose so individual GCs can author their own forms without a schema
    migration. If ``score`` is None the service computes it from the
    answers (sum of truthy values / total non-null answers, x 100).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    questionnaire: dict[str, Any] = Field(default_factory=dict)
    score: int | None = Field(default=None, ge=0, le=100)


class BlockRequest(BaseModel):
    """Hard-block a subcontractor from bidding / payment with a reason."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(..., min_length=1, max_length=2000)


class InsuranceExpiryEntry(BaseModel):
    """One subcontractor flagged by ``check_insurance_expiry``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    insurance_expiry_date: date | None = None
    days_until_expiry: int  # negative if already past
    is_blocked: bool = False


# ── SubcontractorContact ─────────────────────────────────────────────────


class SubcontractorContactCreate(BaseModel):
    """Create payload for SubcontractorContact."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subcontractor_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    primary: bool = False


class SubcontractorContactUpdate(BaseModel):
    """Partial update for SubcontractorContact."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    primary: bool | None = None


class SubcontractorContactResponse(BaseModel):
    """SubcontractorContact returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subcontractor_id: UUID
    name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    primary: bool = False
    created_at: datetime
    updated_at: datetime


# ── PrequalificationApplication ─────────────────────────────────────────


class PrequalificationCreate(BaseModel):
    """Create payload for PrequalificationApplication."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subcontractor_id: UUID
    answers: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(
        default="draft",
        pattern=r"^(draft|submitted|under_review|approved|rejected)$",
    )


class PrequalificationUpdate(BaseModel):
    """Partial update for PrequalificationApplication."""

    model_config = ConfigDict(str_strip_whitespace=True)

    answers: dict[str, Any] | None = None
    status: str | None = Field(
        default=None,
        pattern=r"^(draft|submitted|under_review|approved|rejected)$",
    )
    decision_notes: str | None = None


class PrequalificationResponse(BaseModel):
    """PrequalificationApplication returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subcontractor_id: UUID
    submitted_at: datetime | None = None
    status: str = "draft"
    answers: dict[str, Any] = Field(default_factory=dict)
    reviewer_id: str | None = None
    decision_at: datetime | None = None
    decision_notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


# ── Certificate ──────────────────────────────────────────────────────────


class CertificateCreate(BaseModel):
    """Create payload for Certificate."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subcontractor_id: UUID
    cert_type: str = Field(..., pattern=r"^(insurance|license|iso|safety|bond)$")
    issued_by: str | None = Field(default=None, max_length=255)
    issue_date: date | None = None
    valid_until: date | None = None
    document_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = None


class CertificateUpdate(BaseModel):
    """Partial update for Certificate."""

    model_config = ConfigDict(str_strip_whitespace=True)

    cert_type: str | None = Field(default=None, pattern=r"^(insurance|license|iso|safety|bond)$")
    issued_by: str | None = Field(default=None, max_length=255)
    issue_date: date | None = None
    valid_until: date | None = None
    document_url: str | None = Field(default=None, max_length=1000)
    revoked: bool | None = None
    notes: str | None = None


class CertificateResponse(BaseModel):
    """Certificate returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    subcontractor_id: UUID
    cert_type: str
    issued_by: str | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    document_url: str | None = None
    status: str = "valid"
    revoked: bool = False
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── SubcontractAgreement ─────────────────────────────────────────────────


class AgreementCreate(BaseModel):
    """Create payload for SubcontractAgreement."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subcontractor_id: UUID
    project_id: UUID
    title: str = Field(..., min_length=1, max_length=500)
    total_value: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="", max_length=3)
    start_date: date | None = None
    end_date: date | None = None
    retention_percent: Decimal = Field(default=Decimal("5.0"), ge=0, le=100)
    retention_release_event: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class AgreementUpdate(BaseModel):
    """Partial update for SubcontractAgreement."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=500)
    total_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    start_date: date | None = None
    end_date: date | None = None
    retention_percent: Decimal | None = Field(default=None, ge=0, le=100)
    retention_release_event: str | None = Field(default=None, max_length=120)
    status: str | None = Field(
        default=None,
        pattern=r"^(draft|active|completed|terminated)$",
    )
    notes: str | None = None


class AgreementResponse(BaseModel):
    """SubcontractAgreement returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    subcontractor_id: UUID
    project_id: UUID
    title: str
    total_value: Decimal = Decimal("0")
    currency: str = ""
    start_date: date | None = None
    end_date: date | None = None
    retention_percent: Decimal = Decimal("5.0")
    retention_release_event: str | None = None
    status: str = "draft"
    notes: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── WorkPackage ──────────────────────────────────────────────────────────


class WorkPackageCreate(BaseModel):
    """Create payload for WorkPackage."""

    model_config = ConfigDict(str_strip_whitespace=True)

    agreement_id: UUID
    name: str = Field(..., min_length=1, max_length=500)
    scope: str | None = None
    planned_value: Decimal = Field(default=Decimal("0"), ge=0)
    completion_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    status: str = Field(
        default="planned", pattern=r"^(planned|in_progress|completed)$",
    )


class WorkPackageUpdate(BaseModel):
    """Partial update for WorkPackage."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=500)
    scope: str | None = None
    planned_value: Decimal | None = Field(default=None, ge=0)
    completion_percent: Decimal | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(
        default=None, pattern=r"^(planned|in_progress|completed)$",
    )


class WorkPackageResponse(BaseModel):
    """WorkPackage returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agreement_id: UUID
    name: str
    scope: str | None = None
    planned_value: Decimal = Decimal("0")
    completion_percent: Decimal = Decimal("0")
    status: str = "planned"
    created_at: datetime
    updated_at: datetime


# ── PaymentApplication & Lines ───────────────────────────────────────────


class PaymentApplicationLineCreate(BaseModel):
    """Line item attached to a payment application."""

    model_config = ConfigDict(str_strip_whitespace=True)

    work_package_id: UUID
    claimed_amount: Decimal = Field(default=Decimal("0"), ge=0)
    certified_amount: Decimal = Field(default=Decimal("0"), ge=0)
    approved_amount: Decimal = Field(default=Decimal("0"), ge=0)


class PaymentApplicationLineResponse(BaseModel):
    """Line item returned with a payment application."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_application_id: UUID
    work_package_id: UUID
    claimed_amount: Decimal = Decimal("0")
    certified_amount: Decimal = Decimal("0")
    approved_amount: Decimal = Decimal("0")


class PaymentApplicationCreate(BaseModel):
    """Create payload for PaymentApplication."""

    model_config = ConfigDict(str_strip_whitespace=True)

    agreement_id: UUID
    application_number: str | None = Field(default=None, max_length=40)
    period_start: date | None = None
    period_end: date | None = None
    gross_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="", max_length=3)
    lines: list[PaymentApplicationLineCreate] = Field(default_factory=list)


class PaymentApplicationUpdate(BaseModel):
    """Partial update for PaymentApplication."""

    model_config = ConfigDict(str_strip_whitespace=True)

    period_start: date | None = None
    period_end: date | None = None
    gross_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    rejection_reason: str | None = None


class PaymentApplicationResponse(BaseModel):
    """PaymentApplication returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    agreement_id: UUID
    application_number: str
    period_start: date | None = None
    period_end: date | None = None
    gross_amount: Decimal = Decimal("0")
    retention_amount: Decimal = Decimal("0")
    net_amount: Decimal = Decimal("0")
    currency: str = ""
    status: str = "submitted"
    submitted_at: datetime | None = None
    foreman_approved_at: datetime | None = None
    foreman_approved_by: str | None = None
    finance_approved_at: datetime | None = None
    finance_approved_by: str | None = None
    paid_at: datetime | None = None
    rejection_reason: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Retention ────────────────────────────────────────────────────────────


class RetentionLedgerEntryResponse(BaseModel):
    """RetentionLedger entry returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agreement_id: UUID
    payment_application_id: UUID | None = None
    accrued_amount: Decimal = Decimal("0")
    released_amount: Decimal = Decimal("0")
    released_at: datetime | None = None
    release_reason: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class RetentionReleasePayload(BaseModel):
    """Release retention for an agreement."""

    model_config = ConfigDict(str_strip_whitespace=True)

    agreement_id: UUID
    amount: Decimal = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=255)


# ── Rating ──────────────────────────────────────────────────────────────


class RatingCreate(BaseModel):
    """Create payload for a SubcontractorRating period rollup."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subcontractor_id: UUID
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    quality_score: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    hse_score: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    schedule_score: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    cost_score: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    basis: dict[str, Any] = Field(default_factory=dict)


class RatingResponse(BaseModel):
    """SubcontractorRating returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subcontractor_id: UUID
    period: str
    quality_score: Decimal = Decimal("0")
    hse_score: Decimal = Decimal("0")
    schedule_score: Decimal = Decimal("0")
    cost_score: Decimal = Decimal("0")
    overall_score: Decimal = Decimal("0")
    basis: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


# ── Helpers / dashboards ────────────────────────────────────────────────


class ExpiryAlert(BaseModel):
    """A pending expiry alert for a single certificate."""

    certificate_id: UUID
    subcontractor_id: UUID
    cert_type: str
    valid_until: date
    days_until_expiry: int
    window: int = Field(description="Alert window: 60 / 30 / 7")


class PaymentBlockResult(BaseModel):
    """Result of `next_payment_blocked` check."""

    blocked: bool
    reasons: list[str] = Field(default_factory=list)


class SubcontractorDashboard(BaseModel):
    """Summary statistics for a subcontractor."""

    subcontractor_id: UUID
    legal_name: str
    prequalification_status: str
    rating_score: Decimal = Decimal("0")
    active_agreements: int = 0
    open_payment_applications: int = 0
    pending_retention: Decimal = Decimal("0")
    expired_certificates: int = 0
    expiring_soon_certificates: int = 0
    blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)


# ── Schedule of Values (SOV) summary ──────────────────────────────────────


class SOVRow(BaseModel):
    """One row in a Schedule-of-Values rollup — per work-package totals."""

    work_package_id: UUID
    name: str
    planned_value: Decimal = Decimal("0")
    completion_percent: Decimal = Decimal("0")
    # All claim/cert/approved totals are rolled up across every payment app
    # tied to this work package — current period + all prior periods.
    claimed_to_date: Decimal = Decimal("0")
    certified_to_date: Decimal = Decimal("0")
    approved_to_date: Decimal = Decimal("0")
    remaining: Decimal = Decimal("0")
    status: str = "planned"


class SOVSummaryResponse(BaseModel):
    """Schedule-of-Values rollup for a subcontract agreement."""

    agreement_id: UUID
    subcontractor_id: UUID
    project_id: UUID | None = None
    total_value: Decimal = Decimal("0")
    currency: str = ""
    rows: list[SOVRow] = Field(default_factory=list)
    totals: dict[str, Decimal] = Field(default_factory=dict)


# ── Tax-ID / VAT validator ────────────────────────────────────────────────


class TaxIdValidationRequest(BaseModel):
    """Request payload for tax-id / VAT format validation."""

    model_config = ConfigDict(str_strip_whitespace=True)

    country: str = Field(..., min_length=2, max_length=2)
    tax_id: str = Field(..., min_length=1, max_length=64)


class TaxIdValidationResponse(BaseModel):
    """Result of tax-id format validation.

    NB: this is a *format* check (regex-based), not a live lookup against a
    government registry. The `country` is upper-cased; the `tax_id` is
    returned in the canonical form (uppercase, no spaces / dots / dashes).
    """

    country: str
    tax_id_normalised: str
    format_valid: bool
    standard: str | None = Field(
        default=None,
        description=(
            "Name of the standard the value was checked against — e.g. "
            "'EU VAT', 'US EIN', 'GB VRN'. None if no rule is known for the country."
        ),
    )
    reason: str | None = Field(
        default=None,
        description="Failure reason when format_valid is false; None on success.",
    )
