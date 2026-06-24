# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cost recovery ORM models.

Tables:
    oe_cost_recovery_back_charge - a cost the project intends to recover from
        the responsible party, with its commercial state and amounts.
"""

import uuid
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_types import MoneyType
from app.database import GUID, Base


class BackCharge(Base):
    """A back-charge: a cost recoverable from the party responsible for it."""

    __tablename__ = "oe_cost_recovery_back_charge"

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The originating record (a change order, NCR, defect, delay event). A free
    # reference string so the module stays decoupled from any one source table.
    source_ref: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # Who the cost is charged to: a contact / subcontractor id or a plain label.
    responsible_party: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # How the liability is grounded (a contract clause, an NCR, an instruction).
    basis: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    gross_amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False, default=Decimal("0"))
    # Share of the gross cost judged recoverable, 0..1. NUMERIC(6,4) keeps four
    # decimal places (for example 0.3333) and always reads back as Decimal.
    chargeable_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("1"))
    # Platform rule: no model-/DB-level hardcoded currency. The column defaults
    # to empty; the service stamps the project's currency on create.
    currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="", default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed", index=True)
    recovered_amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False, default=Decimal("0"))
    # ISO-8601 timestamp strings stamped when the back-charge is agreed and when
    # it is fully recovered (String(40) leaves margin for any offset form).
    agreed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recovered_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<BackCharge {self.id} {self.responsible_party!r} {self.status}>"
