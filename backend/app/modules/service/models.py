"""‌⁠‍Service & Maintenance ORM models.

Tables:
    oe_service_contract               — customer-scoped service agreement
    oe_service_asset                  — customer asset under contract
    oe_service_ticket                 — incoming service request
    oe_service_work_order             — dispatched on-site visit
    oe_service_work_order_item        — labor / material / travel line item
    oe_service_debrief                — P-C-S report after a visit
    oe_service_sla_definition         — reusable SLA tier
    oe_service_schedule               — PPM (recurring inspection) schedule
    oe_service_checklist              — reusable inspection checklist template
"""

import uuid
from decimal import Decimal

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import GUID, Base

# ── Contract ──────────────────────────────────────────────────────────────


class ServiceContract(Base):
    """‌⁠‍Service agreement between us (provider) and a customer (Contact).

    A contract scopes assets, tickets and work orders. It is *not* required
    to be linked to a project — service work routinely spans many projects
    or none at all (post-handover maintenance).
    """

    __tablename__ = "oe_service_contract"

    # Customer (a Contact row). Always required.
    # FK declared in alembic migration only; ORM-level FK omitted to avoid
    # metadata-level cross-module coupling in test fixtures.
    customer_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        nullable=False,
        index=True,
    )
    # Optional linkage to a project (e.g. warranty period of a delivered build).
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contract_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ISO date strings — match the convention used in safety/changeorders.
    period_start: Mapped[str] = mapped_column(String(20), nullable=False)
    period_end: Mapped[str] = mapped_column(String(20), nullable=False)

    # Optional FK to a reusable SLA tier. NULL ⇒ ad-hoc / no formal SLA.
    sla_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_service_sla_definition.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sla_tier: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="")

    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    assets: Mapped[list["ServiceAsset"]] = relationship(
        "app.modules.service.models.ServiceAsset",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tickets: Mapped[list["ServiceTicket"]] = relationship(
        "app.modules.service.models.ServiceTicket",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ServiceContract {self.contract_number} ({self.status})>"


# ── Asset ─────────────────────────────────────────────────────────────────


class ServiceAsset(Base):
    """‌⁠‍A serviceable customer asset (boiler, AHU, lift, generator, etc.)."""

    __tablename__ = "oe_service_asset"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_service_contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    install_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    warranty_until: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    contract: Mapped[ServiceContract] = relationship(
        "app.modules.service.models.ServiceContract",
        back_populates="assets",
    )

    def __repr__(self) -> str:
        return f"<ServiceAsset {self.asset_tag or self.id} ({self.asset_type}/{self.status})>"


# ── Ticket ────────────────────────────────────────────────────────────────


class ServiceTicket(Base):
    """A request for service — created manually or via customer portal."""

    __tablename__ = "oe_service_ticket"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_service_contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_service_asset.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticket_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="med", index=True)

    # ISO 8601 timestamps. SLA-due is computed at create time from the
    # contract's SLA definition (response_time_minutes).
    reported_at: Mapped[str] = mapped_column(String(40), nullable=False)
    sla_due_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", index=True)
    # Channel the ticket came in on. Used by the dispatcher to triage portal
    # vs phone-in tickets and to audit SLA reporting per channel.
    # One of: manual, portal, email, api, auto_ppm.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", server_default="manual", index=True,
    )
    reported_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    resolved_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Set once when the first SLA-breach event is emitted, so we don't re-emit
    # for the same ticket on every scan tick.
    sla_breach_notified_at: Mapped[str | None] = mapped_column(
        String(40), nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    contract: Mapped[ServiceContract] = relationship(
        "app.modules.service.models.ServiceContract",
        back_populates="tickets",
    )
    work_orders: Mapped[list["ServiceWorkOrder"]] = relationship(
        "app.modules.service.models.ServiceWorkOrder",
        back_populates="ticket",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ServiceTicket {self.ticket_number} ({self.status}/{self.priority})>"


# ── Work Order ────────────────────────────────────────────────────────────


class ServiceWorkOrder(Base):
    """A dispatched on-site visit answering one or more ticket needs."""

    __tablename__ = "oe_service_work_order"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_service_ticket.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduled_for: Mapped[str | None] = mapped_column(String(40), nullable=True)
    technician_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled", index=True
    )
    debrief_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    customer_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    billed_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    billed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    ticket: Mapped[ServiceTicket] = relationship(
        "app.modules.service.models.ServiceTicket",
        back_populates="work_orders",
    )
    items: Mapped[list["ServiceWorkOrderItem"]] = relationship(
        "app.modules.service.models.ServiceWorkOrderItem",
        back_populates="work_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    debriefs: Mapped[list["DebriefReport"]] = relationship(
        "app.modules.service.models.DebriefReport",
        back_populates="work_order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ServiceWorkOrder {self.work_order_number} ({self.status})>"


class ServiceWorkOrderItem(Base):
    """A single labor / material / travel line within a work order."""

    __tablename__ = "oe_service_work_order_item"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_service_work_order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="labor")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    unit_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    # Stored, not computed: lets you record an override price for a billable
    # line (e.g. warranty-covered labor at zero) without losing the rate.
    total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0")
    )
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    work_order: Mapped[ServiceWorkOrder] = relationship(
        "app.modules.service.models.ServiceWorkOrder",
        back_populates="items",
    )

    def __repr__(self) -> str:
        return f"<ServiceWorkOrderItem {self.item_type} {self.quantity}{self.unit} @ {self.unit_rate}>"


# ── Debrief / SLA / Schedule / Checklist ──────────────────────────────────


class DebriefReport(Base):
    """Problem-Cause-Solution (P-C-S) report after a service visit.

    Stored separately from ServiceWorkOrder.debrief_summary so we can later index
    P-C-S triples for semantic search ("find similar past failures").
    """

    __tablename__ = "oe_service_debrief"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_service_work_order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cause: Mapped[str] = mapped_column(Text, nullable=False, default="")
    solution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    root_cause_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    follow_up_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    work_order: Mapped[ServiceWorkOrder] = relationship(
        "app.modules.service.models.ServiceWorkOrder",
        back_populates="debriefs",
    )

    def __repr__(self) -> str:
        return f"<DebriefReport wo={self.work_order_id} cat={self.root_cause_category}>"


class SLADefinition(Base):
    """A reusable SLA tier (response/resolution time + severity matrix)."""

    __tablename__ = "oe_service_sla_definition"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    response_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=240)
    resolution_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    # JSON list/dict mapping severity → time targets (high, med, low...).
    severity_levels: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<SLADefinition {self.name} ({self.response_time_minutes}min)>"


class ServiceSchedule(Base):
    """PPM (preventive maintenance) schedule attached to an asset."""

    __tablename__ = "oe_service_schedule"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_service_asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="quarterly"
    )
    next_due_date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    last_completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    checklist_template_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_service_checklist.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<ServiceSchedule asset={self.asset_id} freq={self.frequency} next={self.next_due_date}>"


class AssetInspectionChecklist(Base):
    """A reusable inspection checklist template.

    `items` is a JSON list of dicts: [{question, type, required, options?}].
    """

    __tablename__ = "oe_service_checklist"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    asset_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    items: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata", JSON, nullable=False, default=dict, server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<AssetInspectionChecklist {self.name} ({len(self.items or [])} items)>"
