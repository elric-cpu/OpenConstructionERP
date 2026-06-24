# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cost recovery service - the thin persistence layer over the back_charge engine.

Stores back-charge records for a project and feeds their present state to the
pure :mod:`back_charge` engine to produce the recovery ledger. Writes follow the
platform convention: the service flushes, and the request-scoped session
dependency commits, so a failed request rolls back cleanly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.cost_recovery.back_charge import (
    STATUS_AGREED,
    STATUS_RECOVERED,
    BackChargeItem,
    RecoveryLedger,
    build_ledger,
)
from app.modules.cost_recovery.models import BackCharge
from app.modules.cost_recovery.schemas import BackChargeCreate, BackChargeUpdate
from app.modules.projects.models import Project


async def _resolve_currency(session: AsyncSession, project_id: uuid.UUID, currency: str) -> str:
    """Use the supplied currency, else stamp the project's currency, else blank."""
    if currency and currency.strip():
        return currency.strip()
    project = await session.get(Project, project_id)
    if project is not None and project.currency:
        return str(project.currency)
    return ""


def to_back_charge_item(bc: BackCharge) -> BackChargeItem:
    """Project a stored back-charge row to the pure engine's input dataclass."""
    return BackChargeItem(
        ref_id=str(bc.id),
        responsible_party=bc.responsible_party or "",
        description=bc.description or "",
        basis=bc.basis or "",
        gross_amount=bc.gross_amount if bc.gross_amount is not None else Decimal("0"),
        chargeable_pct=bc.chargeable_pct if bc.chargeable_pct is not None else Decimal("0"),
        currency=bc.currency or "",
        status=bc.status or "",
        recovered_amount=bc.recovered_amount if bc.recovered_amount is not None else Decimal("0"),
    )


async def create_back_charge(
    session: AsyncSession,
    project_id: uuid.UUID,
    payload: BackChargeCreate,
    *,
    created_by: str | None = None,
) -> BackCharge:
    """Record a new back-charge for a project and announce it on the timeline."""
    currency = await _resolve_currency(session, project_id, payload.currency)
    back_charge = BackCharge(
        project_id=project_id,
        source_ref=payload.source_ref or "",
        responsible_party=payload.responsible_party or "",
        description=payload.description or "",
        basis=payload.basis or "",
        gross_amount=payload.gross_amount if payload.gross_amount is not None else Decimal("0"),
        chargeable_pct=payload.chargeable_pct if payload.chargeable_pct is not None else Decimal("1"),
        currency=currency,
        status=payload.status or "proposed",
        created_by=created_by,
    )
    session.add(back_charge)
    await session.flush()

    # The "cost." prefix is on the timeline allowlist and the payload carries a
    # project id, so this lands on the project timeline. publish_detached defers
    # past the request commit, so the row is durable by the time it fans out.
    event_bus.publish_detached(
        "cost.back_charge.recorded",
        {
            "project_id": str(project_id),
            "back_charge_id": str(back_charge.id),
            "responsible_party": back_charge.responsible_party,
            "status": back_charge.status,
        },
        source_module="cost_recovery",
    )
    return back_charge


async def list_back_charges(session: AsyncSession, project_id: uuid.UUID) -> list[BackCharge]:
    """Return every back-charge for a project, oldest first."""
    stmt = select(BackCharge).where(BackCharge.project_id == project_id).order_by(BackCharge.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def get_back_charge(
    session: AsyncSession,
    project_id: uuid.UUID,
    back_charge_id: uuid.UUID,
) -> BackCharge | None:
    """Return one back-charge scoped to its project, or None if absent."""
    stmt = select(BackCharge).where(
        BackCharge.project_id == project_id,
        BackCharge.id == back_charge_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_back_charge(
    session: AsyncSession,
    project_id: uuid.UUID,
    back_charge_id: uuid.UUID,
    payload: BackChargeUpdate,
) -> BackCharge | None:
    """Apply a partial update and stamp the agreed / recovered timestamps."""
    back_charge = await get_back_charge(session, project_id, back_charge_id)
    if back_charge is None:
        return None

    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(back_charge, key, value)

    now_iso = datetime.now(UTC).isoformat()
    new_status = fields.get("status")
    if new_status == STATUS_AGREED and not back_charge.agreed_at:
        back_charge.agreed_at = now_iso
    if new_status == STATUS_RECOVERED and not back_charge.recovered_at:
        back_charge.recovered_at = now_iso

    await session.flush()
    return back_charge


async def build_recovery_ledger(session: AsyncSession, project_id: uuid.UUID) -> RecoveryLedger:
    """Roll a project's back-charges into a per-party / per-currency ledger."""
    rows = await list_back_charges(session, project_id)
    return build_ledger(to_back_charge_item(row) for row in rows)
