# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Cost recovery API routes (auto-mounted at /api/v1/cost-recovery).

Records and rolls up back-charges for a project. Every route is project-scoped:
the caller must hold the module capability (read or write) and pass
:func:`verify_project_access` for the project, which 404s on both "missing" and
"denied" so it never leaks project existence.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.cost_recovery.models import BackCharge
from app.modules.cost_recovery.schemas import (
    BackChargeCreate,
    BackChargeOut,
    BackChargeUpdate,
    CurrencyRecoveryOut,
    PartyRecoveryOut,
    RecoveryLedgerOut,
)
from app.modules.cost_recovery.service import (
    build_recovery_ledger,
    create_back_charge,
    list_back_charges,
    to_back_charge_item,
    update_back_charge,
)

router = APIRouter(tags=["Cost Recovery"])


def _serialize(back_charge: BackCharge) -> BackChargeOut:
    """Render a stored back-charge with its derived amounts as money strings."""
    item = to_back_charge_item(back_charge)
    return BackChargeOut(
        id=str(back_charge.id),
        project_id=str(back_charge.project_id),
        source_ref=back_charge.source_ref or "",
        responsible_party=back_charge.responsible_party or "",
        description=back_charge.description or "",
        basis=back_charge.basis or "",
        gross_amount=str(item.gross_amount),
        chargeable_pct=str(back_charge.chargeable_pct if back_charge.chargeable_pct is not None else "0"),
        chargeable_amount=str(item.chargeable_amount),
        currency=back_charge.currency or "",
        status=back_charge.status or "",
        recovered_amount=str(item.recovered_amount),
        outstanding=str(item.outstanding),
        is_open=item.is_open,
        agreed_at=back_charge.agreed_at,
        recovered_at=back_charge.recovered_at,
    )


@router.get(
    "/projects/{project_id}/back-charges",
    response_model=list[BackChargeOut],
    dependencies=[Depends(RequirePermission("cost_recovery.read"))],
)
async def list_project_back_charges(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> list[BackChargeOut]:
    """List every back-charge recorded against a project."""
    await verify_project_access(project_id, user_id or "", session)
    rows = await list_back_charges(session, project_id)
    return [_serialize(row) for row in rows]


@router.post(
    "/projects/{project_id}/back-charges",
    response_model=BackChargeOut,
    dependencies=[Depends(RequirePermission("cost_recovery.write"))],
)
async def create_project_back_charge(
    project_id: uuid.UUID,
    payload: BackChargeCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> BackChargeOut:
    """Record a new back-charge for a project."""
    await verify_project_access(project_id, user_id or "", session)
    back_charge = await create_back_charge(session, project_id, payload, created_by=user_id)
    return _serialize(back_charge)


@router.patch(
    "/projects/{project_id}/back-charges/{back_charge_id}",
    response_model=BackChargeOut,
    dependencies=[Depends(RequirePermission("cost_recovery.write"))],
)
async def update_project_back_charge(
    project_id: uuid.UUID,
    back_charge_id: uuid.UUID,
    payload: BackChargeUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> BackChargeOut:
    """Update a back-charge (amounts, responsible party, or commercial status)."""
    await verify_project_access(project_id, user_id or "", session)
    back_charge = await update_back_charge(session, project_id, back_charge_id, payload)
    if back_charge is None:
        raise HTTPException(status_code=404, detail="Back-charge not found")
    return _serialize(back_charge)


@router.get(
    "/projects/{project_id}/recovery-ledger",
    response_model=RecoveryLedgerOut,
    dependencies=[Depends(RequirePermission("cost_recovery.read"))],
)
async def get_recovery_ledger(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> RecoveryLedgerOut:
    """Roll the project's back-charges into a per-party / per-currency ledger."""
    await verify_project_access(project_id, user_id or "", session)
    ledger = await build_recovery_ledger(session, project_id)
    return RecoveryLedgerOut(
        project_id=str(project_id),
        item_count=ledger.item_count,
        open_count=ledger.open_count,
        primary_currency=ledger.primary_currency,
        primary_outstanding=str(ledger.primary_outstanding),
        by_party=[
            PartyRecoveryOut(
                party=p.party,
                currency=p.currency,
                item_count=p.item_count,
                open_count=p.open_count,
                gross_total=str(p.gross_total),
                chargeable_total=str(p.chargeable_total),
                recovered_total=str(p.recovered_total),
                outstanding_total=str(p.outstanding_total),
            )
            for p in ledger.by_party
        ],
        by_currency=[
            CurrencyRecoveryOut(
                currency=c.currency,
                item_count=c.item_count,
                chargeable_total=str(c.chargeable_total),
                recovered_total=str(c.recovered_total),
                outstanding_total=str(c.outstanding_total),
            )
            for c in ledger.by_currency
        ],
    )
