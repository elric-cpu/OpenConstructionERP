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
    """A buyer / lead linked to a plot (eventually)."""

    __tablename__ = "oe_property_dev_buyer"
    __table_args__ = (
        UniqueConstraint(
            "plot_id", name="uq_oe_property_dev_buyer_plot"
        ),
    )

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


__all__ = [
    "Buyer",
    "BuyerOption",
    "BuyerOptionGroup",
    "BuyerSelection",
    "BuyerSelectionItem",
    "Development",
    "Handover",
    "HandoverDoc",
    "HouseType",
    "HouseTypeVariant",
    "Plot",
    "Snag",
    "WarrantyClaim",
]


# Unused import sentinels for tooling: DateTime is used implicitly through
# String(20) ISO date columns; suppress lint by referencing here.
_unused = (DateTime, Date)
