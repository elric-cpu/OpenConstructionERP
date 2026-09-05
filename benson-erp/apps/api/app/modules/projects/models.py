import uuid
from decimal import Decimal

from sqlalchemy import Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import TenantRecord


class Contract(TenantRecord, Base):
    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("tenant_id", "proposal_id"),)

    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contract_number: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Project(TenantRecord, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "proposal_id"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contract_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_number: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="SETUP")


class BudgetLine(TenantRecord, Base):
    __tablename__ = "budget_lines"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    source_estimate_line_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    original_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    revised_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
