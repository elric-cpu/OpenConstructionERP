"""‌⁠‍Property Development ORM models.

Tables (all prefixed ``oe_property_dev_``):
    development          — top-level development (1:1 with a Project)
    house_type           — reusable house type within a development
    house_type_variant   — price-modifying variant of a house type
    plot                 — sale-able plot within a development
    buyer_option_group   — group of buyer-selectable options (kitchen, bathroom, ...)
    buyer_option         — individual option (with price delta, lead time, ...)
    buyer                — buyer / lead linked to a plot
    buyer_selection      — buyer's current options selection
    buyer_selection_item — single line within a buyer selection
    handover             — handover ceremony / snag record per plot
    snag                 — defect noted during/after handover
    warranty_claim       — post-handover warranty claim

External references (kept as plain UUID columns, NO FK):
    portal_user_id              → oe_portal_user.id  (Module 21)
    bim_model_ref               → canonical BIM model id (string)
    linked_service_ticket_id    → oe_service_ticket.id  (Module 18)
"""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: F401  — used in Mapped[datetime] annotations
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

# ── Development ─────────────────────────────────────────────────────────


class Development(Base):
    """‌⁠‍A property development — a collection of plots tied to one project."""

    __tablename__ = "oe_property_dev_development"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    location_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_plots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sales_phase: Mapped[str] = mapped_column(
        String(40), nullable=False, default="planning", index=True
    )
    launch_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    marketing_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", index=True
    )
    units: Mapped[str] = mapped_column(String(16), nullable=False, default="metric")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Development {self.code} ({self.sales_phase}/{self.status})>"


# ── House Types & Variants ──────────────────────────────────────────────


class HouseType(Base):
    """‌⁠‍A reusable house type / model within a development."""

    __tablename__ = "oe_property_dev_house_type"
    __table_args__ = (
        UniqueConstraint(
            "development_id", "code", name="uq_oe_property_dev_house_type_dev_code"
        ),
    )

    development_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    bedrooms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bathrooms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_area_m2: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    footprint_m2: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    levels: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    # Canonical BIM model id — NO FK (intentional, see module docstring).
    bim_model_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<HouseType {self.code} ({self.bedrooms}BR/{self.total_area_m2}m2)>"


class HouseTypeVariant(Base):
    """A price-modifying variant of a house type (mirror, extra bedroom, ...)."""

    __tablename__ = "oe_property_dev_house_type_variant"
    __table_args__ = (
        UniqueConstraint(
            "house_type_id", "code", name="uq_oe_property_dev_variant_house_code"
        ),
    )

    house_type_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_house_type.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Modifier as percentage points off base_price (e.g. 5.50 = +5.5%).
    modifier_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<HouseTypeVariant {self.code} ({self.modifier_pct}%)>"


# ── Plot ────────────────────────────────────────────────────────────────


class Plot(Base):
    """A sale-able plot within a development."""

    __tablename__ = "oe_property_dev_plot"
    __table_args__ = (
        UniqueConstraint(
            "development_id", "plot_number", name="uq_oe_property_dev_plot_dev_number"
        ),
    )

    development_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_number: Mapped[str] = mapped_column(String(50), nullable=False)
    house_type_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_house_type.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    house_type_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_house_type_variant.id", ondelete="SET NULL"),
        nullable=True,
    )
    orientation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    area_m2: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    garden_area_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    price_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="planned", index=True
    )
    reservation_deadline: Mapped[str | None] = mapped_column(String(20), nullable=True)
    construction_status_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Plot {self.plot_number} ({self.status})>"


# ── Buyer Option Catalogue ──────────────────────────────────────────────


class BuyerOptionGroup(Base):
    """A group of buyer-selectable options (kitchen, bathroom, flooring, ...)."""

    __tablename__ = "oe_property_dev_buyer_option_group"
    __table_args__ = (
        UniqueConstraint(
            "development_id",
            "code",
            name="uq_oe_property_dev_option_group_dev_code",
        ),
    )

    development_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    group_type: Mapped[str] = mapped_column(String(40), nullable=False, default="extras")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allow_multiple: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    freeze_offset_days_before_handover: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<BuyerOptionGroup {self.code} ({self.group_type})>"


class BuyerOption(Base):
    """A single buyer-selectable option."""

    __tablename__ = "oe_property_dev_buyer_option"

    group_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer_option_group.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    price_delta: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    # JSON compatibility rules. Schema:
    #   {"must_have": ["opt_code", ...], "must_not_have": ["opt_code", ...]}
    compatibility_rules: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<BuyerOption {self.code} ({self.price_delta})>"


# ── Buyer ───────────────────────────────────────────────────────────────


class Buyer(Base):
    """A buyer / lead linked to a plot (eventually).

    Note: The historical ``UniqueConstraint(plot_id)`` was dropped in
    v3103 to support multi-buyer SPAs via :class:`ContractParty`
    (joint ownership, co-borrowers, guarantors). Application logic
    must enforce one-primary-buyer-per-plot at the service layer.
    """

    __tablename__ = "oe_property_dev_buyer"

    development_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_plot.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Plain UUID — refers to oe_portal_user.id but NOT a FK (cross-module).
    portal_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="lead", index=True
    )
    contract_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    contract_signed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    deposit_paid_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    freeze_deadline: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Deposit accounting — drives forfeiture rules per jurisdiction.
    deposit_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    deposit_forfeited: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    deposit_refunded: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    # ISO 3166-1 alpha-2 country code — selects forfeiture rules.
    jurisdiction: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default=""
    )
    cancelled_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cancelled_reason: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=""
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Buyer {self.full_name!s} ({self.status})>"


# ── Buyer Selection ─────────────────────────────────────────────────────


class BuyerSelection(Base):
    """A buyer's current selection of options."""

    __tablename__ = "oe_property_dev_buyer_selection"

    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="draft", index=True
    )
    submitted_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    locked_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_options_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<BuyerSelection buyer={self.buyer_id} status={self.status}>"


class BuyerSelectionItem(Base):
    """A single line inside a buyer's selection."""

    __tablename__ = "oe_property_dev_buyer_selection_item"

    selection_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer_selection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    option_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer_option.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    total_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    included_in_production: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<SelectionItem option={self.option_id} qty={self.quantity}>"


# ── Handover ────────────────────────────────────────────────────────────


class Handover(Base):
    """A handover ceremony / state record per plot (one per plot)."""

    __tablename__ = "oe_property_dev_handover"
    __table_args__ = (
        UniqueConstraint("plot_id", name="uq_oe_property_dev_handover_plot"),
    )

    plot_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_plot.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheduled_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    snag_count_at_handover: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    final_check_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    keys_handed_over_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_signature_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Handover plot={self.plot_id} completed={self.completed_at}>"


class HandoverDoc(Base):
    """A document delivered to the buyer at handover.

    Handover-doc bundle (CDM 2015 Reg 32–35 / Building Safety Act):
    warranty cert, instructions/manuals, key receipt, H&S file, EPC,
    NHBC cert, ...).  ``is_required=True`` means handover is incomplete
    until the doc is delivered.
    """

    __tablename__ = "oe_property_dev_handover_doc"

    handover_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_handover.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivered_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<HandoverDoc {self.doc_type} ({'delivered' if self.is_delivered else 'pending'})>"


class Snag(Base):
    """A defect noted during/after handover."""

    __tablename__ = "oe_property_dev_snag"

    handover_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_handover.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_in_plot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="minor", index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", index=True
    )
    reported_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fixed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fix_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Snag handover={self.handover_id} ({self.severity}/{self.status})>"


# ── Warranty ────────────────────────────────────────────────────────────


class WarrantyClaim(Base):
    """A post-handover warranty claim."""

    __tablename__ = "oe_property_dev_warranty_claim"

    plot_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_plot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raised_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="defect", index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="raised", index=True
    )
    accepted_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    closed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Cross-module ref to oe_service_ticket.id — plain UUID, NO FK.
    linked_service_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<WarrantyClaim plot={self.plot_id} "
            f"({self.category}/{self.status})>"
        )


# ── R6: Lead / Reservation / SalesContract / PaymentSchedule ────────────


class Lead(Base):
    """A sales lead — separate from :class:`Buyer`.

    A Lead can predate any plot/buyer relationship (top-of-funnel). On
    conversion the service creates a Reservation (and optionally a
    Buyer) and sets ``converted_to_buyer_id``.
    """

    __tablename__ = "oe_property_dev_lead"

    development_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Multi-tenant column — nullable for single-tenant deployments.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="other", index=True
    )
    lead_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    assigned_agent_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="new", index=True
    )
    nurture_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", index=True
    )
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    preferred_house_type_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_house_type.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_to_buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Lead {self.full_name!s} ({self.status}/{self.source})>"


class Reservation(Base):
    """A standalone plot reservation backed by a deposit.

    FSM: ``active`` -> ``converted | expired | cancelled``. Terminal
    states are ``converted`` / ``expired`` / ``cancelled`` /
    ``refunded`` — once entered the row is read-only at the service
    layer.
    """

    __tablename__ = "oe_property_dev_reservation"
    __table_args__ = (
        UniqueConstraint(
            "plot_id",
            "reservation_number",
            name="uq_oe_property_dev_reservation_plot_number",
        ),
    )

    plot_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_plot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_lead.id", ondelete="SET NULL"),
        nullable=True,
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="SET NULL"),
        nullable=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    reservation_number: Mapped[str] = mapped_column(String(80), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="")
    deposit_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cooling_off_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    cooling_off_until: Mapped[str | None] = mapped_column(  # ISO date
        String(20), nullable=True
    )
    expires_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Reservation {self.reservation_number} ({self.status})>"


class SalesContract(Base):
    """Sale & Purchase Agreement (SPA) for a plot.

    Multi-buyer is supported through :class:`ContractParty` rows;
    each contract may have one ``primary`` party and any number of
    ``co_owner`` / ``guarantor`` / ``power_of_attorney`` parties whose
    ``ownership_pct`` must sum to 100 (enforced in service).
    """

    __tablename__ = "oe_property_dev_sales_contract"
    __table_args__ = (
        UniqueConstraint(
            "plot_id",
            "contract_number",
            name="uq_oe_property_dev_sales_contract_plot_number",
        ),
    )

    contract_number: Mapped[str] = mapped_column(String(80), nullable=False)
    plot_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_plot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_reservation.id", ondelete="SET NULL"),
        nullable=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    signing_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # ISO 3166-2 region code (e.g. "DE-BE", "GB-ENG"). Optional —
    # falls back to the development's jurisdiction at write time.
    governing_law: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    # {base, vat, stamp_duty, legal_fees, options_value, discounts}
    total_price_breakdown: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="")
    e_sign_envelope_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="draft", index=True
    )
    parent_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_sales_contract.id", ondelete="SET NULL"),
        nullable=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Template-version reference (e.g. "spa-template-v3.2").
    terms_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<SalesContract {self.contract_number} ({self.status})>"


class SalesContractRevision(Base):
    """Versioned terms snapshot of a :class:`SalesContract`.

    Captures the full terms blob each time the contract is amended so
    later disputes can prove which exact wording was in force at any
    given signing date.
    """

    __tablename__ = "oe_property_dev_sales_contract_revision"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "revision_number",
            name="uq_oe_property_dev_sales_contract_revision_rev",
        ),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_sales_contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    terms_blob: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SalesContractRevision contract={self.contract_id} "
            f"rev={self.revision_number}>"
        )


class PaymentSchedule(Base):
    """Parent payment schedule per :class:`SalesContract` (1:1).

    The schedule's instalments fire on either an absolute ``due_date``
    or a milestone event (e.g. ``foundation_complete``) that is
    published by the ``schedule`` module.
    """

    __tablename__ = "oe_property_dev_payment_schedule"
    __table_args__ = (
        UniqueConstraint(
            "sales_contract_id",
            name="uq_oe_property_dev_payment_schedule_contract",
        ),
    )

    sales_contract_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_sales_contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="")
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    late_fee_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<PaymentSchedule contract={self.sales_contract_id} ({self.status})>"


class Instalment(Base):
    """A single instalment line inside a :class:`PaymentSchedule`.

    Becomes ``due`` when its ``milestone_event`` fires or the date
    rolls past ``due_date``. Late-fee accrual is a daily delta of
    ``schedule.late_fee_pct * outstanding`` after the grace period.
    """

    __tablename__ = "oe_property_dev_instalment"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id",
            "sequence",
            name="uq_oe_property_dev_instalment_schedule_seq",
        ),
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_payment_schedule.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    milestone_label: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    # When this event publishes through the event bus the line moves to
    # ``due`` (e.g. ``reservation`` | ``spa_signed`` | ``foundation_complete``
    # | ``structure_complete`` | ``handover``).
    milestone_event: Mapped[str] = mapped_column(
        String(80), nullable=False, default="", index=True
    )
    due_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending", index=True
    )
    late_fee_accrued: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    invoice_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<Instalment schedule={self.schedule_id} #{self.sequence} "
            f"({self.status})>"
        )


class ContractParty(Base):
    """Junction row connecting a buyer to a :class:`SalesContract`.

    Supports multi-buyer SPAs (joint ownership, co-borrowers,
    guarantors, PoA). ``ownership_pct`` of all parties in a contract
    must sum to exactly 100 — enforced at the service layer.
    """

    __tablename__ = "oe_property_dev_contract_party"
    __table_args__ = (
        UniqueConstraint(
            "sales_contract_id",
            "buyer_id",
            name="uq_oe_property_dev_contract_party_contract_buyer",
        ),
    )

    sales_contract_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_sales_contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ownership_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    party_role: Mapped[str] = mapped_column(
        String(40), nullable=False, default="primary"
    )
    signing_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signature_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<ContractParty contract={self.sales_contract_id} "
            f"buyer={self.buyer_id} ({self.party_role}/{self.ownership_pct}%)>"
        )


__all__ = [
    "Buyer",
    "BuyerOption",
    "BuyerOptionGroup",
    "BuyerSelection",
    "BuyerSelectionItem",
    "ContractParty",
    "Development",
    "Handover",
    "HandoverDoc",
    "HouseType",
    "HouseTypeVariant",
    "Instalment",
    "Lead",
    "PaymentSchedule",
    "Plot",
    "Reservation",
    "SalesContract",
    "SalesContractRevision",
    "Snag",
    "WarrantyClaim",
]


# Unused import sentinel for tooling: ``Date`` referenced solely to keep
# lint happy while we transition String(20) date columns to real Date.
_unused = (Date,)
