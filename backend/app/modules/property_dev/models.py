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
    Index,
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Type of development (residential, mixed_use, commercial, ...). Free-form
    # string at the model layer; the schema layer enforces an enum so future
    # additions (e.g. ``industrial_park``) don't require a DB migration.
    dev_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="residential", server_default="residential"
    )
    location_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ISO-3166 alpha-2 country code (DE, US, UK, ...). Drives the
    # house-type catalogue picker and the tax engine.
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    # Geo coordinates (WGS84). Stored as Numeric so we don't lose precision
    # round-tripping through SQLite. Optional — only populated when the
    # operator pins the development on the map.
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    total_plots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_area_m2: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    total_floors: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    sales_phase: Mapped[str] = mapped_column(
        String(40), nullable=False, default="planning", index=True
    )
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    launch_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    completion_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    marketing_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="active", index=True
    )
    units: Mapped[str] = mapped_column(String(16), nullable=False, default="metric")
    # Total sales target in ``currency``. Used by the dashboard's progress bar
    # and by the EAC / cashflow forecasts.
    sales_target_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    # ISO-4217 currency. Empty-string default == "fall back to the parent
    # project's currency at read time"; the service layer never auto-fills
    # this with a hard-coded "EUR" (see v3 DB-level EUR-default kill).
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default=""
    )
    # People / orgs. Kept as free-form strings instead of FK to Companies
    # because (a) Companies module is optional and (b) the developer can
    # often be a JV that doesn't have a tidy row in any directory.
    developer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    architect_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    general_contractor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Marketing assets — URLs only. File uploads belong to the Documents
    # module; this column just stores the canonical link.
    cover_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    brochure_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
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
    # Task #138: Phase/Block hierarchy — Plot belongs to a Block, Block belongs
    # to a Phase, Phase belongs to a Development. All FKs nullable so legacy
    # Plot rows (created before the hierarchy existed) keep working.
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_block.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    level_in_block: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_on_floor: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    orientation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Free-text label kept until a future task replaces this with a
    # user-creatable HouseType catalogue (tracked separately).
    house_type_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Compass / cardinal view subject — sea, mountain, garden, courtyard,
    # street, park, other. Kept as String (not enum) so a developer can
    # add bespoke values per project without a migration.
    view_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    area_m2: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    garden_area_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    balcony_area_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    storage_area_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    # Per-plot bedroom / bathroom override. Defaults to 0 so the form
    # column is always present. The HouseType row carries the "default"
    # for a model — these per-plot fields capture deviations
    # (e.g. converted study -> bedroom).
    bedrooms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    bathrooms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    parking_spaces: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Best-effort average daily sun exposure. Optional — most listings
    # don't have this measured, but high-end / passive-house brochures do.
    sun_exposure_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2), nullable=True
    )
    # ``price_base`` = explicit override (priority 1).
    # ``computed_price`` = cached value from PriceMatrix.compute(plot) (prio 2).
    # Effective price helper lives in service.compute_plot_price().
    price_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    computed_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
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
    # ── Contacts bridge ────────────────────────────────────────────
    # Optional FK back to the canonical contact row in
    # ``oe_contacts_contact``. The Contact owns name/email/phone as the
    # single source of truth; the Buyer keeps only buyer-specific
    # fields (status, contract_value, deposit_*, …). Nullable for
    # legacy rows + portal-side anonymous buyers.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_contacts_contact.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    """A defect noted during/after handover.

    ``buyer_id`` is a nullable cross-link to the buyer who raised it (when
    raised post-handover via the buyer portal); during the handover
    ceremony itself snags are usually surveyor-raised and ``buyer_id``
    is left NULL.

    ``cost_impact`` is the estimated repair cost. Stored as
    ``Numeric(18, 2)`` so monetary rollups stay Decimal-exact.

    ``category`` aligns with the punchlist categories so the snag ->
    punchlist auto-bridge can copy it 1:1.

    ``photos`` is a JSON list of relative paths (uploaded via magic-byte
    gated /api/v1/property-dev/snags/{id}/photos/).
    """

    __tablename__ = "oe_property_dev_snag"

    handover_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_handover.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional cross-link: who raised it (buyer-portal snags). NULL for
    # surveyor / contractor / project-team raised snags.
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="general", server_default="general",
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
    # Estimated repair cost. Decimal so rollups stay exact.
    cost_impact: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0",
    )
    # Relative paths under uploads/snag/photos/. Magic-byte gated upload.
    photos: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]",
    )
    # Best-effort link to the auto-created punchlist item. NOT a FK
    # (cross-module); plain UUID string. NULL when bridge skipped or
    # punchlist module disabled.
    linked_punch_item_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Snag handover={self.handover_id} ({self.severity}/{self.status})>"


# ── Warranty ────────────────────────────────────────────────────────────


class WarrantyClaim(Base):
    """A post-handover warranty claim.

    Extended in v3113 with deep-integration columns so the UI can:
      * file the claim against a specific handover (warranty period
        is computed from ``Handover.completed_at`` + the configured
        warranty years — see ``WarrantyClaimResponse.is_in_warranty``).
      * assign the claim to a contractor / PM (``assigned_to_user_id``).
      * attach magic-byte-validated photos (``photos`` JSON list of
        relative storage paths, mirrors ``Snag.photos``).
      * track an SLA deadline (``sla_deadline``) and resolution notes.
      * bridge an upstream Snag (``source_snag_id``) so a single defect
        flows snag → punchlist + warranty cleanly.
    """

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
    # Optional cross-link: which handover (and thus which warranty
    # window) the claim is filed against. SET NULL on handover delete
    # so the claim survives if a defective handover is rolled back.
    handover_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_handover.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Optional upstream Snag this claim was raised from (so we don't
    # duplicate the same defect across snag + warranty). SET NULL on
    # snag delete.
    source_snag_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_snag.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Optional assignee — contractor / PM responsible for resolution.
    # No FK on oe_users_user (cross-module ref kept loose; matches the
    # rest of property_dev's external-ref convention).
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    raised_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(
        String(40), nullable=False, default="defect", index=True
    )
    # NOTE: severity mirrors Snag.severity (minor/major/critical) — used
    # for SLA escalation in the UI.
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="minor",
        server_default="minor",
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON list of relative storage paths (uploaded via magic-byte gated
    # /api/v1/property-dev/warranty-claims/{id}/photos/). Mirrors
    # ``Snag.photos`` shape so the UI gallery component can be shared.
    photos: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="raised", index=True
    )
    sla_deadline: Mapped[str | None] = mapped_column(String(20), nullable=True)
    accepted_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    closed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # ── Contacts bridge ────────────────────────────────────────────
    # Optional FK back to the canonical contact row. The Contact owns
    # name/email/phone; the Lead keeps lead-specific fields (score,
    # source, status, …). Nullable for legacy rows.
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_contacts_contact.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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




# ── Phase / Block hierarchy (task #138) ─────────────────────────────────


class Phase(Base):
    """A sales/build phase within a Development (e.g. "Launch Q3 2026").

    Phases group Blocks; Blocks group Plots. The hierarchy lets phased
    multi-tower / multi-cluster developments stage launches without
    creating a separate Development row per release.
    """

    __tablename__ = "oe_property_dev_phase"
    __table_args__ = (
        UniqueConstraint(
            "development_id", "code", name="uq_oe_property_dev_phase_dev_code"
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
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    planned_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    planned_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="planned", index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Phase {self.code} ({self.status})>"


class Block(Base):
    """A building / cluster within a Phase. Groups Plots by level/position."""

    __tablename__ = "oe_property_dev_block"
    __table_args__ = (
        UniqueConstraint(
            "phase_id", "code", name="uq_oe_property_dev_block_phase_code"
        ),
    )

    phase_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_phase.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    levels_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    units_per_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    orientation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    geo_coordinates: Mapped[dict | None] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="planned", index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Block {self.code} ({self.status})>"


# ── Broker / Commission (task #138) ─────────────────────────────────────


class Broker(Base):
    """External property broker / agent that brings in deals.

    Carries a KYC lifecycle (pending → verified → expired/rejected). A broker
    can have many CommissionAgreements (one per development or one global).
    """

    __tablename__ = "oe_property_dev_broker"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "license_number",
            name="uq_oe_property_dev_broker_tenant_license",
        ),
    )

    # Multi-tenant key. Held as a plain UUID (no FK) — mirrors the
    # cross-module convention used elsewhere in property_dev.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    license_number: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", index=True
    )
    # ISO 3166-2 region (e.g. "AE-DU", "RU-MOW"); broader than ISO 3166-1.
    jurisdiction: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", index=True
    )
    contact_email: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_commission_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    kyc_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    kyc_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return f"<Broker {self.name!r} ({self.kyc_status})>"


class CommissionAgreement(Base):
    """A broker's commission contract on a development (or all developments).

    ``structure_type`` determines the shape of the ``structure`` JSONB:
      - ``flat``:    ``{"amount": "5000", "currency": "EUR"}``
      - ``percent``: ``{"pct": "2.50"}``
      - ``ladder``:  ``{"tiers": [{"threshold": "100000", "pct": "1.5"}, ...]}``

    ``accrual_trigger`` controls which event lifecycle stage flips this
    agreement into an accrual: lead_qualified / reservation_paid /
    spa_signed (default) / handover_complete.
    """

    __tablename__ = "oe_property_dev_commission_agreement"

    broker_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_broker.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable → applies to ALL developments for this broker.
    development_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Array of plot UUIDs (as strings) — empty/null means "all plots".
    specific_plot_ids: Mapped[list | None] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=True
    )
    structure_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="percent"
    )
    structure: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    accrual_trigger: Mapped[str] = mapped_column(
        String(40), nullable=False, default="spa_signed", index=True
    )
    payout_terms: Mapped[str] = mapped_column(
        String(20), nullable=False, default="net30"
    )
    withholding_tax_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    effective_from: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<CommissionAgreement broker={self.broker_id} "
            f"{self.structure_type} ({self.status})>"
        )


class CommissionAccrual(Base):
    """A concrete commission earned by a broker on a specific event.

    State machine: accrued → approved → paid (or cancelled at any step).
    Approval + payment gates are MANAGER+ only.
    """

    __tablename__ = "oe_property_dev_commission_accrual"

    agreement_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_property_dev_commission_agreement.id", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    broker_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_broker.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_event: Mapped[str] = mapped_column(
        String(40), nullable=False, default="", index=True
    )
    trigger_entity_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default=""
    )
    trigger_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    commission_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accrued", index=True
    )
    accrued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    withholding_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    net_payable: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<CommissionAccrual broker={self.broker_id} "
            f"{self.commission_amount}{self.currency} ({self.state})>"
        )


# ── Escrow (task #138) ──────────────────────────────────────────────────


class EscrowAccount(Base):
    """A regulator-supervised escrow account holding buyer instalments.

    One Development can have multiple accounts — typically one per currency
    + regulator (RERA AED, MAHARERA INR, etc).
    """

    __tablename__ = "oe_property_dev_escrow_account"
    __table_args__ = (
        UniqueConstraint(
            "development_id", "currency", "regulator_ref",
            name="uq_oe_property_dev_escrow_dev_ccy_reg",
        ),
    )

    development_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    regulator_ref: Mapped[str] = mapped_column(
        String(40), nullable=False, default="other", index=True
    )
    regulator_account_number: Mapped[str] = mapped_column(
        String(120), nullable=False, default=""
    )
    bank_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    iban: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    swift_bic: Mapped[str] = mapped_column(
        String(16), nullable=False, default=""
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    opened_at: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    closed_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<EscrowAccount dev={self.development_id} "
            f"{self.currency} ({self.regulator_ref})>"
        )


class EscrowTransaction(Base):
    """A single debit/credit movement on an escrow account."""

    __tablename__ = "oe_property_dev_escrow_transaction"

    escrow_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey(
            "oe_property_dev_escrow_account.id", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(
        String(8), nullable=False, default="credit"
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="instalment", index=True
    )
    # Plain UUID (no FK) — instalment lives in PaymentSchedule (task #137).
    source_instalment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    source_reference: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    bank_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    transaction_date: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", index=True
    )
    reconciliation_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unreconciled", index=True
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reconciled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<EscrowTx {self.direction} {self.amount}{self.currency} "
            f"({self.reconciliation_state})>"
        )


# ── PriceMatrix (task #138) ─────────────────────────────────────────────


class PriceMatrix(Base):
    """A versioned price grid that computes plot prices via JSONB rules.

    ``rules`` is an ordered list of factor descriptors::

        [
          {"factor_type": "floor",          "condition": {"min": 5},   "multiplier": "1.04"},
          {"factor_type": "view",           "condition": {"value": "sea"}, "multiplier": "1.15"},
          {"factor_type": "corner",         "condition": {"value": true},  "multiplier": "1.08"},
          {"factor_type": "launch_discount","condition": {"before": "2026-09-01"}, "multiplier": "0.97"},
          {"factor_type": "phase_escalator","condition": {"phase_code": "P2"}, "multiplier": "1.06"}
        ]

    Final price = plot.area_m2 * base_price_per_m2 * ∏ multipliers.
    """

    __tablename__ = "oe_property_dev_price_matrix"

    development_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_development.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    base_price_per_m2: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    effective_from: Mapped[str] = mapped_column(
        String(20), nullable=False, default="", index=True
    )
    effective_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rules: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}"
    )

    def __repr__(self) -> str:
        return (
            f"<PriceMatrix {self.name!r} v{self.version} ({self.status})>"
        )




# ── House Type Catalogue (user-extensible, country-scoped presets) ──────


class PropertyDevHouseType(Base):
    """A user-creatable / preset house-type entry for the Plot picker.

    Distinct from :class:`HouseType` (which is per-Development and carries
    full pricing/area/bedroom data). This catalogue is a lightweight
    classification list used when filling out a Plot — the user picks
    e.g. "Reihenhaus" or "Townhouse" without committing to a specific
    floor plan. The chosen entry is stored on the Plot via metadata
    (``metadata.house_type_catalogue_id``) so the existing
    ``Plot.house_type_id`` FK to dev-scoped HouseType is unaffected.

    Scoping:
      - ``project_id IS NULL`` + ``is_preset=True`` → global preset
        (shipped via migration seed; visible to every tenant).
      - ``project_id`` set → user-created entry, only visible to that
        project's owner.

    ``code`` is a short UPPER_SNAKE identifier ("REIHENHAUS",
    "TOWNHOUSE"); ``name`` is the localised display label. The
    ``(project_id, country_code, code)`` unique constraint lets two
    projects keep the same code and lets a project override a preset
    by creating its own row with the same ``code``.
    """

    __tablename__ = "oe_property_dev_house_type_catalogue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "country_code",
            "code",
            name="uq_oe_property_dev_house_type_catalogue_proj_country_code",
        ),
        Index(
            "ix_oe_property_dev_house_type_catalogue_proj_country",
            "project_id",
            "country_code",
        ),
    )

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # ISO 3166-1 alpha-2 country code; NULL for region-agnostic entries.
    # Stored upper-case ("DE", "US"). When the operator picks "Other /
    # Custom region" in the UI we store NULL here and the free-text tag
    # lands in :attr:`region_label` below.
    country_code: Mapped[str | None] = mapped_column(
        String(2), nullable=True, index=True
    )
    # Free-text region label, used either when the operator picks
    # "Other / Custom region" (e.g. "EU-wide", "DACH", "Middle East") or
    # as an extra qualifier alongside ``country_code``. Optional.
    region_label: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_typical_m2: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    floors_typical: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Layout — purely typical/illustrative, the actual Plot row carries
    # the source-of-truth quantities. Kept nullable so partial info is OK.
    typical_bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    typical_bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # On-plot parking — typical count of parking spots (driveway + garage
    # + carport, whichever the operator wants to advertise). Nullable so
    # multi-family schemes that don't advertise per-unit parking can omit
    # the value. Capped at 10 by the schema validator.
    parking_spots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pricing — both bounds optional so the operator can store a single-
    # ended hint ("from 250k", "up to 1.2M"). ``currency`` is ISO 4217.
    typical_price_min: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    typical_price_max: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # Free strings so tenants can extend without a schema change. The UI
    # constrains them to a curated dropdown but the storage stays open.
    construction_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    energy_class: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    sales_channel: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Free-form tag list. JSON (not JSONB) because SQLite-compat — this
    # is settings data, never queried by content.
    tags: Mapped[list] = mapped_column(  # type: ignore[type-arg]
        JSON, nullable=False, default=list, server_default="[]"
    )
    is_preset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", index=True
    )
    # Owning user — NULL for migration-seeded presets. Plain UUID, NOT a
    # FK to oe_users_user (cross-module convention; SET NULL on user
    # delete would need a real FK with on-delete callback, which we
    # explicitly avoid here to match the rest of property_dev).
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<PropertyDevHouseType {self.code} "
            f"({self.country_code or '*'}, "
            f"{'preset' if self.is_preset else 'custom'})>"
        )


class PropertyDevCustomTemplate(Base):
    """User-uploaded document template (.docx / .html / .pdf).

    Settings page entry alongside the six built-in PDF generators in
    :mod:`app.modules.property_dev.document_templates`. The actual
    template file is written to ``uploads/property_dev/custom_templates/``
    by the upload endpoint; the row carries only metadata.

    Scoping: ``project_id`` is the owning project (and matches every
    other property_dev row). ``development_id`` is optional — populated
    when the operator wants a template available only inside a
    specific development context (the settings page's "set default
    for current development" toggle persists this client-side).

    ``doc_type`` is intentionally a free string: tenants may want to
    introduce types beyond the six built-ins ("brokerage_commission",
    "kyc_checklist", "payment_reminder", "snag_report", "invoice", ...).
    Validation lives in the upload endpoint (length + allowed
    characters), not at the database layer.
    """

    __tablename__ = "oe_property_dev_custom_template"

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Optional development scope (no FK — same convention as the rest
    # of property_dev cross-table refs).
    development_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="custom", server_default="custom",
        index=True,
    )
    entity: Mapped[str] = mapped_column(
        String(40), nullable=False, default="custom", server_default="custom"
    )
    trigger: Mapped[str] = mapped_column(
        String(200), nullable=False, default="manual", server_default="manual"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<PropertyDevCustomTemplate {self.name} "
            f"({self.doc_type}, {self.filename})>"
        )


# ── Buyer Self-Service Portal magic-link tokens (v3124) ─────────────────


class PortalToken(Base):
    """Audit + revocation registry for buyer-portal magic-link JWTs.

    Each row is the persisted counterpart of a ``scope='portal'`` JWT
    issued at SPA / Reservation creation. The JWT itself stays stateless
    (verifiable from ``JWT_SECRET`` alone) but we keep the ``jti`` on
    this row so an operator can REVOKE a leaked link — the verify path
    rejects any matching ``jti`` whose ``revoked_at`` is set, regardless
    of the JWT's in-flight ``exp`` claim.

    The buyer / reservation / SPA scope columns drive the per-endpoint
    IDOR guard so a buyer cannot swap UUIDs in the URL to read another
    buyer's payment schedule or signed documents — the guard re-checks
    that ``doc.buyer_id == token.buyer_id`` on every read.

    Per the v3119 fresh-install lock-cascade memory: every NOT NULL
    column has a ``server_default``. SQLAlchemy ``create_all`` ignores
    Python ``default=`` so the DB-level default is the only safe path
    for greenfield installs.
    """

    __tablename__ = "oe_propdev_portal_token"

    buyer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_reservation.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sales_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_property_dev_sales_contract.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # ``jti`` claim of the JWT. Unique-indexed so a single SQL lookup
    # answers "is this token revoked?" without scanning. 64 chars covers
    # any uuid4-hex / urlsafe-token shape we might use.
    jwt_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="",
        unique=True, index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_used_ip: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
    )
    # Plain UUID (no FK) — matches the cross-module convention used
    # elsewhere in property_dev to dodge a hard dep on oe_users_user.
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return (
            f"<PortalToken buyer={self.buyer_id} "
            f"revoked={self.revoked_at is not None}>"
        )


__all__ = [
    "Block",
    "Broker",
    "Buyer",
    "BuyerOption",
    "BuyerOptionGroup",
    "BuyerSelection",
    "BuyerSelectionItem",
    "CommissionAccrual",
    "CommissionAgreement",
    "ContractParty",
    "Development",
    "EscrowAccount",
    "EscrowTransaction",
    "Handover",
    "HandoverDoc",
    "HouseType",
    "HouseTypeVariant",
    "Instalment",
    "Lead",
    "PaymentSchedule",
    "Phase",
    "Plot",
    "PortalToken",
    "PriceMatrix",
    "PropertyDevCustomTemplate",
    "PropertyDevHouseType",
    "Reservation",
    "SalesContract",
    "SalesContractRevision",
    "Snag",
    "WarrantyClaim",
]


# Unused import sentinel for tooling: ``Date`` referenced solely to keep
# lint happy while we transition String(20) ISO date columns to real Date.
_unused = (Date,)
