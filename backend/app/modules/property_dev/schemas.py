"""Property Development Pydantic schemas — request/response models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Development ─────────────────────────────────────────────────────────


class DevelopmentCreate(BaseModel):
    """Create a new development."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(default="", max_length=255)
    location_address: str | None = None
    total_plots: int = Field(default=0, ge=0)
    sales_phase: str = Field(
        default="planning",
        pattern=r"^(planning|launch|sales|handover|closed)$",
    )
    launch_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    completion_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    marketing_brief: str | None = None
    status: str = Field(default="active", pattern=r"^(active|paused|completed)$")
    units: str = Field(default="metric", pattern=r"^(metric|imperial)$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DevelopmentUpdate(BaseModel):
    """Partial update for a development."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    location_address: str | None = None
    total_plots: int | None = Field(default=None, ge=0)
    sales_phase: str | None = Field(
        default=None, pattern=r"^(planning|launch|sales|handover|closed)$"
    )
    launch_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    completion_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    marketing_brief: str | None = None
    status: str | None = Field(default=None, pattern=r"^(active|paused|completed)$")
    units: str | None = Field(default=None, pattern=r"^(metric|imperial)$")
    metadata: dict[str, Any] | None = None


class DevelopmentResponse(BaseModel):
    """Development returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    code: str
    name: str = ""
    location_address: str | None = None
    total_plots: int = 0
    sales_phase: str = "planning"
    launch_date: str | None = None
    completion_date: str | None = None
    marketing_brief: str | None = None
    status: str = "active"
    units: str = "metric"
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── House Type ──────────────────────────────────────────────────────────


class HouseTypeCreate(BaseModel):
    """Create a new house type."""

    model_config = ConfigDict(str_strip_whitespace=True)

    development_id: UUID
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(default="", max_length=255)
    bedrooms: int = Field(default=0, ge=0)
    bathrooms: int = Field(default=0, ge=0)
    total_area_m2: Decimal = Field(default=Decimal("0"), ge=0)
    footprint_m2: Decimal = Field(default=Decimal("0"), ge=0)
    levels: int = Field(default=1, ge=1)
    base_price: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="", max_length=8)
    bim_model_ref: str | None = Field(default=None, max_length=120)
    thumbnail_url: str | None = Field(default=None, max_length=1024)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HouseTypeUpdate(BaseModel):
    """Partial update for a house type."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    total_area_m2: Decimal | None = Field(default=None, ge=0)
    footprint_m2: Decimal | None = Field(default=None, ge=0)
    levels: int | None = Field(default=None, ge=1)
    base_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    bim_model_ref: str | None = Field(default=None, max_length=120)
    thumbnail_url: str | None = Field(default=None, max_length=1024)
    description: str | None = None
    metadata: dict[str, Any] | None = None


class HouseTypeResponse(BaseModel):
    """House type returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    development_id: UUID
    code: str
    name: str = ""
    bedrooms: int = 0
    bathrooms: int = 0
    total_area_m2: Decimal = Decimal("0")
    footprint_m2: Decimal = Decimal("0")
    levels: int = 1
    base_price: Decimal = Decimal("0")
    currency: str = ""
    bim_model_ref: str | None = None
    thumbnail_url: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── House Type Variant ──────────────────────────────────────────────────


class HouseTypeVariantCreate(BaseModel):
    """Create a new house type variant."""

    model_config = ConfigDict(str_strip_whitespace=True)

    house_type_id: UUID
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(default="", max_length=255)
    modifier_pct: Decimal = Field(default=Decimal("0"))
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HouseTypeVariantUpdate(BaseModel):
    """Partial update for a variant."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    modifier_pct: Decimal | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None


class HouseTypeVariantResponse(BaseModel):
    """Variant returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    house_type_id: UUID
    code: str
    name: str = ""
    modifier_pct: Decimal = Decimal("0")
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Plot ────────────────────────────────────────────────────────────────


class PlotCreate(BaseModel):
    """Create a new plot."""

    model_config = ConfigDict(str_strip_whitespace=True)

    development_id: UUID
    plot_number: str = Field(..., min_length=1, max_length=50)
    house_type_id: UUID | None = None
    house_type_variant_id: UUID | None = None
    orientation: str | None = Field(default=None, max_length=16)
    area_m2: Decimal = Field(default=Decimal("0"), ge=0)
    garden_area_m2: Decimal | None = Field(default=None, ge=0)
    price_base: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="", max_length=8)
    status: str = Field(
        default="planned",
        pattern=r"^(planned|reserved|under_construction|ready|sold|handed_over)$",
    )
    reservation_deadline: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    construction_status_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlotUpdate(BaseModel):
    """Partial update for a plot."""

    model_config = ConfigDict(str_strip_whitespace=True)

    house_type_id: UUID | None = None
    house_type_variant_id: UUID | None = None
    orientation: str | None = Field(default=None, max_length=16)
    area_m2: Decimal | None = Field(default=None, ge=0)
    garden_area_m2: Decimal | None = Field(default=None, ge=0)
    price_base: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    status: str | None = Field(
        default=None,
        pattern=r"^(planned|reserved|under_construction|ready|sold|handed_over)$",
    )
    reservation_deadline: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    construction_status_percent: Decimal | None = Field(default=None, ge=0, le=100)
    metadata: dict[str, Any] | None = None


class PlotResponse(BaseModel):
    """Plot returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    development_id: UUID
    plot_number: str
    house_type_id: UUID | None = None
    house_type_variant_id: UUID | None = None
    orientation: str | None = None
    area_m2: Decimal = Decimal("0")
    garden_area_m2: Decimal | None = None
    price_base: Decimal = Decimal("0")
    currency: str = ""
    status: str = "planned"
    reservation_deadline: str | None = None
    construction_status_percent: Decimal = Decimal("0")
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class PlotReserveRequest(BaseModel):
    """Payload for /plots/{id}/reserve."""

    model_config = ConfigDict(str_strip_whitespace=True)

    buyer_id: UUID | None = None
    full_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    language: str = Field(default="en", max_length=10)
    reservation_deadline: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Buyer Option Group ──────────────────────────────────────────────────


class BuyerOptionGroupCreate(BaseModel):
    """Create a buyer option group."""

    model_config = ConfigDict(str_strip_whitespace=True)

    development_id: UUID
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(default="", max_length=255)
    group_type: str = Field(
        default="extras",
        pattern=r"^(kitchen|bathroom|flooring|extras|exterior|technology|other)$",
    )
    display_order: int = Field(default=0, ge=0)
    allow_multiple: bool = False
    max_count: int | None = Field(default=None, ge=1)
    freeze_offset_days_before_handover: int = Field(default=60, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyerOptionGroupUpdate(BaseModel):
    """Partial update for a buyer option group."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    group_type: str | None = Field(
        default=None,
        pattern=r"^(kitchen|bathroom|flooring|extras|exterior|technology|other)$",
    )
    display_order: int | None = Field(default=None, ge=0)
    allow_multiple: bool | None = None
    max_count: int | None = Field(default=None, ge=1)
    freeze_offset_days_before_handover: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class BuyerOptionGroupResponse(BaseModel):
    """Buyer option group returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    development_id: UUID
    code: str
    name: str = ""
    group_type: str = "extras"
    display_order: int = 0
    allow_multiple: bool = False
    max_count: int | None = None
    freeze_offset_days_before_handover: int = 60
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Buyer Option ────────────────────────────────────────────────────────


class BuyerOptionCreate(BaseModel):
    """Create a buyer option."""

    model_config = ConfigDict(str_strip_whitespace=True)

    group_id: UUID
    code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(default="", max_length=255)
    sku: str | None = Field(default=None, max_length=120)
    price_delta: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="", max_length=8)
    lead_time_days: int = Field(default=0, ge=0)
    supplier_name: str | None = Field(default=None, max_length=255)
    thumbnail_url: str | None = Field(default=None, max_length=1024)
    is_active: bool = True
    compatibility_rules: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyerOptionUpdate(BaseModel):
    """Partial update for a buyer option."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=120)
    price_delta: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)
    lead_time_days: int | None = Field(default=None, ge=0)
    supplier_name: str | None = Field(default=None, max_length=255)
    thumbnail_url: str | None = Field(default=None, max_length=1024)
    is_active: bool | None = None
    compatibility_rules: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class BuyerOptionResponse(BaseModel):
    """Buyer option returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    group_id: UUID
    code: str
    name: str = ""
    sku: str | None = None
    price_delta: Decimal = Decimal("0")
    currency: str = ""
    lead_time_days: int = 0
    supplier_name: str | None = None
    thumbnail_url: str | None = None
    is_active: bool = True
    compatibility_rules: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Buyer ───────────────────────────────────────────────────────────────


class BuyerCreate(BaseModel):
    """Create a buyer / lead."""

    model_config = ConfigDict(str_strip_whitespace=True)

    development_id: UUID
    plot_id: UUID | None = None
    portal_user_id: UUID | None = None
    full_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    language: str = Field(default="en", max_length=10)
    status: str = Field(
        default="lead",
        pattern=r"^(lead|reserved|contracted|completed|cancelled)$",
    )
    contract_value: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="", max_length=8)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyerUpdate(BaseModel):
    """Partial update for a buyer."""

    model_config = ConfigDict(str_strip_whitespace=True)

    plot_id: UUID | None = None
    portal_user_id: UUID | None = None
    full_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    language: str | None = Field(default=None, max_length=10)
    status: str | None = Field(
        default=None,
        pattern=r"^(lead|reserved|contracted|completed|cancelled)$",
    )
    contract_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    contract_signed_at: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    deposit_paid_at: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    freeze_deadline: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    metadata: dict[str, Any] | None = None


class BuyerResponse(BaseModel):
    """Buyer returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    development_id: UUID
    plot_id: UUID | None = None
    portal_user_id: UUID | None = None
    full_name: str = ""
    email: str = ""
    phone: str | None = None
    language: str = "en"
    status: str = "lead"
    contract_value: Decimal = Decimal("0")
    currency: str = ""
    contract_signed_at: str | None = None
    deposit_paid_at: str | None = None
    freeze_deadline: str | None = None
    deposit_amount: Decimal = Decimal("0")
    deposit_forfeited: Decimal = Decimal("0")
    deposit_refunded: Decimal = Decimal("0")
    jurisdiction: str = ""
    cancelled_at: str | None = None
    cancelled_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class BuyerContractRequest(BaseModel):
    """Payload for /buyers/{id}/contract."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_value: Decimal = Field(..., ge=0)
    currency: str = Field(..., min_length=1, max_length=8)
    contract_signed_at: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    deposit_paid_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    freeze_deadline: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    jurisdiction: str | None = Field(default=None, max_length=8)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyerCancelRequest(BaseModel):
    """Payload for /buyers/{id}/cancel — cancel + compute forfeiture."""

    model_config = ConfigDict(str_strip_whitespace=True)

    cancelled_at: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason: str = Field(default="", max_length=500)
    jurisdiction_override: str | None = Field(default=None, max_length=8)


class DepositForfeitureResponse(BaseModel):
    """Result of a deposit-forfeiture computation."""

    buyer_id: UUID
    jurisdiction: str
    deposit_amount: Decimal = Decimal("0")
    forfeited_amount: Decimal = Decimal("0")
    refundable_amount: Decimal = Decimal("0")
    rule_citation: str = ""
    rule_summary: str = ""


# ── Buyer Selection ─────────────────────────────────────────────────────


class BuyerSelectionCreate(BaseModel):
    """Create a buyer selection."""

    model_config = ConfigDict(str_strip_whitespace=True)

    buyer_id: UUID
    status: str = Field(
        default="draft", pattern=r"^(draft|submitted|locked|cancelled)$"
    )
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyerSelectionUpdate(BaseModel):
    """Partial update for a buyer selection."""

    model_config = ConfigDict(str_strip_whitespace=True)

    status: str | None = Field(
        default=None, pattern=r"^(draft|submitted|locked|cancelled)$"
    )
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class BuyerSelectionResponse(BaseModel):
    """Buyer selection returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    buyer_id: UUID
    status: str = "draft"
    submitted_at: str | None = None
    locked_at: str | None = None
    total_options_value: Decimal = Decimal("0")
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class BuyerSelectionItemCreate(BaseModel):
    """Create a buyer selection item."""

    model_config = ConfigDict(str_strip_whitespace=True)

    option_id: UUID
    quantity: int = Field(default=1, ge=1)
    unit_price_snapshot: Decimal | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuyerSelectionItemResponse(BaseModel):
    """Buyer selection item returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    selection_id: UUID
    option_id: UUID
    quantity: int = 1
    unit_price_snapshot: Decimal = Decimal("0")
    total_price: Decimal = Decimal("0")
    included_in_production: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Handover & Snag ─────────────────────────────────────────────────────


class HandoverCreate(BaseModel):
    """Create a handover record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    plot_id: UUID
    scheduled_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoverUpdate(BaseModel):
    """Partial update for a handover record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    scheduled_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    completed_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    snag_count_at_handover: int | None = Field(default=None, ge=0)
    final_check_passed: bool | None = None
    keys_handed_over_at: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    customer_signature_ref: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class HandoverResponse(BaseModel):
    """Handover record returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    plot_id: UUID
    scheduled_at: str | None = None
    completed_at: str | None = None
    snag_count_at_handover: int = 0
    final_check_passed: bool = False
    keys_handed_over_at: str | None = None
    customer_signature_ref: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class HandoverCompleteRequest(BaseModel):
    """Payload for /handovers/{id}/complete."""

    model_config = ConfigDict(str_strip_whitespace=True)

    completed_at: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    customer_signature_ref: str = Field(..., min_length=1, max_length=255)
    keys_handed_over_at: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    final_check_passed: bool = True
    snag_count_at_handover: int = Field(default=0, ge=0)
    notes: str | None = None


class SnagCreate(BaseModel):
    """Create a snag entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    handover_id: UUID
    location_in_plot: str | None = Field(default=None, max_length=255)
    severity: str = Field(
        default="minor", pattern=r"^(cosmetic|minor|major|safety)$"
    )
    description: str = Field(..., min_length=1)
    status: str = Field(
        default="open", pattern=r"^(open|in_progress|fixed|wont_fix)$"
    )
    reported_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SnagUpdate(BaseModel):
    """Partial update for a snag entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    location_in_plot: str | None = Field(default=None, max_length=255)
    severity: str | None = Field(
        default=None, pattern=r"^(cosmetic|minor|major|safety)$"
    )
    description: str | None = Field(default=None, min_length=1)
    status: str | None = Field(
        default=None, pattern=r"^(open|in_progress|fixed|wont_fix)$"
    )
    fixed_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    fix_notes: str | None = None
    metadata: dict[str, Any] | None = None


class SnagResponse(BaseModel):
    """Snag returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    handover_id: UUID
    location_in_plot: str | None = None
    severity: str = "minor"
    description: str = ""
    status: str = "open"
    reported_at: str | None = None
    fixed_at: str | None = None
    fix_notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Warranty ────────────────────────────────────────────────────────────


class WarrantyClaimCreate(BaseModel):
    """Create a warranty claim."""

    model_config = ConfigDict(str_strip_whitespace=True)

    plot_id: UUID
    buyer_id: UUID
    raised_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    category: str = Field(
        default="defect", pattern=r"^(defect|snag|service)$"
    )
    description: str = Field(..., min_length=1)
    status: str = Field(
        default="raised",
        pattern=r"^(raised|under_review|accepted|rejected|closed)$",
    )
    linked_service_ticket_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WarrantyClaimUpdate(BaseModel):
    """Partial update for a warranty claim."""

    model_config = ConfigDict(str_strip_whitespace=True)

    category: str | None = Field(
        default=None, pattern=r"^(defect|snag|service)$"
    )
    description: str | None = Field(default=None, min_length=1)
    status: str | None = Field(
        default=None,
        pattern=r"^(raised|under_review|accepted|rejected|closed)$",
    )
    accepted_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    closed_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    linked_service_ticket_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class WarrantyClaimResponse(BaseModel):
    """Warranty claim returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    plot_id: UUID
    buyer_id: UUID
    raised_at: str | None = None
    category: str = "defect"
    description: str = ""
    status: str = "raised"
    accepted_at: str | None = None
    closed_at: str | None = None
    linked_service_ticket_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Composite responses ─────────────────────────────────────────────────


class PlotPricingResponse(BaseModel):
    """Pricing breakdown for a plot."""

    plot_id: UUID
    base_price: Decimal
    variant_modifier_value: Decimal = Decimal("0")
    selections_total: Decimal = Decimal("0")
    final_price: Decimal
    currency: str = ""


class BuyerConfiguratorResponse(BaseModel):
    """Configurator state for a buyer on a plot."""

    plot: PlotResponse
    house_type: HouseTypeResponse | None = None
    variant: HouseTypeVariantResponse | None = None
    option_groups: list[BuyerOptionGroupResponse] = Field(default_factory=list)
    options_by_group: dict[str, list[BuyerOptionResponse]] = Field(default_factory=dict)
    current_selection: BuyerSelectionResponse | None = None
    current_items: list[BuyerSelectionItemResponse] = Field(default_factory=list)
    pricing: PlotPricingResponse | None = None


class DevelopmentDashboard(BaseModel):
    """Sales dashboard KPIs for a development."""

    development_id: UUID
    total_plots: int = 0
    plots_by_status: dict[str, int] = Field(default_factory=dict)
    buyers_by_status: dict[str, int] = Field(default_factory=dict)
    contracted_value: Decimal = Decimal("0")
    open_snags: int = 0
    open_warranty_claims: int = 0
    completed_handovers: int = 0
    scheduled_handovers: int = 0
    sell_through_percent: Decimal = Decimal("0")


# ── Handover docs ───────────────────────────────────────────────────────


_HANDOVER_DOC_TYPES = r"^(warranty|manual|key_receipt|hs_file|epc|nhbc|inspection_cert|certificate_completion|insurance|other)$"


class HandoverDocCreate(BaseModel):
    """Create a handover document entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    handover_id: UUID
    doc_type: str = Field(..., pattern=_HANDOVER_DOC_TYPES)
    title: str = Field(default="", max_length=255)
    file_url: str | None = Field(default=None, max_length=1024)
    is_required: bool = False
    is_delivered: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoverDocUpdate(BaseModel):
    """Patch a handover document entry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=255)
    file_url: str | None = Field(default=None, max_length=1024)
    is_required: bool | None = None
    is_delivered: bool | None = None
    metadata: dict[str, Any] | None = None


class HandoverDocResponse(BaseModel):
    """Handover doc returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    handover_id: UUID
    doc_type: str
    title: str = ""
    file_url: str | None = None
    is_required: bool = False
    is_delivered: bool = False
    delivered_at: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="metadata_"
    )
    created_at: datetime
    updated_at: datetime


class HandoverBundleResponse(BaseModel):
    """Aggregate of all handover docs + missing-required-doc warning."""

    handover_id: UUID
    docs: list[HandoverDocResponse] = Field(default_factory=list)
    delivered_count: int = 0
    required_count: int = 0
    missing_required: list[str] = Field(default_factory=list)
    ready_for_handover: bool = True


# ── Sales pipeline kanban ───────────────────────────────────────────────


class SalesKanbanBuyerCard(BaseModel):
    """One buyer card on the kanban."""

    buyer_id: UUID
    full_name: str
    email: str = ""
    plot_id: UUID | None = None
    plot_number: str | None = None
    status: str
    contract_value: Decimal = Decimal("0")
    currency: str = ""
    contract_signed_at: str | None = None
    freeze_deadline: str | None = None


class SalesKanbanColumn(BaseModel):
    """One column on the kanban (one status)."""

    status: str
    buyers: list[SalesKanbanBuyerCard] = Field(default_factory=list)
    count: int = 0
    total_value: Decimal = Decimal("0")


class SalesKanbanResponse(BaseModel):
    """Kanban response — one column per buyer-status."""

    development_id: UUID
    columns: list[SalesKanbanColumn] = Field(default_factory=list)


# ── Reservation calendar ────────────────────────────────────────────────


class ReservationCalendarEntry(BaseModel):
    """One entry on the reservation calendar."""

    plot_id: UUID
    plot_number: str
    buyer_id: UUID | None = None
    buyer_name: str = ""
    reservation_deadline: str | None = None
    freeze_deadline: str | None = None
    status: str


class ReservationCalendarResponse(BaseModel):
    """All upcoming reservation-related deadlines for a development."""

    development_id: UUID
    period_start: str
    period_end: str
    entries: list[ReservationCalendarEntry] = Field(default_factory=list)


# ── Development P&L ─────────────────────────────────────────────────────


class DevelopmentPnLResponse(BaseModel):
    """Aggregate P&L for a development.

    Reads from CRM/finance via the cross-module events; service-layer
    aggregates contract revenue + actual costs + deposit retention.
    """

    development_id: UUID
    currency: str = ""
    mixed_currency: bool = False
    revenue_contracted: Decimal = Decimal("0")
    revenue_completed: Decimal = Decimal("0")
    deposits_held: Decimal = Decimal("0")
    deposits_forfeited: Decimal = Decimal("0")
    plot_count_sold: int = 0
    plot_count_handed_over: int = 0
    avg_sale_price: Decimal = Decimal("0")
    open_warranty_count: int = 0
    open_snag_count: int = 0
