import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord
from app.modules.estimating.calculations import PricingMode


class EstimateStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"


class Estimate(TenantRecord, Base):
    __tablename__ = "estimates"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[EstimateStatus] = mapped_column(
        Enum(EstimateStatus), default=EstimateStatus.DRAFT
    )
    pricing_mode: Mapped[PricingMode] = mapped_column(Enum(PricingMode), nullable=False)
    pricing_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"))
    direct_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EstimateSection(TenantRecord, Base):
    __tablename__ = "estimate_sections"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    estimate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)


class EstimateLine(TenantRecord, Base):
    __tablename__ = "estimate_lines"

    estimate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    section_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)


class Proposal(TenantRecord, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "estimate_id", "document_version"),
    )

    estimate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    document_version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus), default=ProposalStatus.DRAFT
    )
    scope_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_name: Mapped[str | None] = mapped_column(String(200))
    acceptance_ip: Mapped[str | None] = mapped_column(String(64))
    acceptance_user_agent: Mapped[str | None] = mapped_column(String(1000))
    acceptance_statement: Mapped[str | None] = mapped_column(Text)
    accepted_document_checksum: Mapped[str | None] = mapped_column(String(64))
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
