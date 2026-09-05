import uuid
from enum import StrEnum

from sqlalchemy import Enum, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class LeadStatus(StrEnum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    SITE_VISIT_SCHEDULED = "SITE_VISIT_SCHEDULED"
    INSPECTION_COMPLETE = "INSPECTION_COMPLETE"
    ESTIMATE_IN_PROGRESS = "ESTIMATE_IN_PROGRESS"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"


class Lead(TenantRecord, Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("tenant_id", "id"),)

    contact_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class Customer(TenantRecord, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "normalized_email"),
    )

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))


class Property(TenantRecord, Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "normalized_address"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    address_line_1: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    normalized_address: Mapped[str] = mapped_column(String(400), nullable=False)
