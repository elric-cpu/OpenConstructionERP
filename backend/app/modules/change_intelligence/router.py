# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Change-intelligence API routes (auto-mounted at /api/v1/change-intelligence).

Access control mirrors every other project-scoped router: the caller must be
authenticated and pass :func:`verify_project_access` for the requested project
(owner / team-member / admin), which 404s on both "missing" and "denied" so it
never leaks project existence.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.change_intelligence.schemas import (
    ClarifiedRequestOut,
    ClarifyIn,
    CommsDigestOut,
    CoordinationPlanOut,
    CoordinationStepOut,
    CurrencyImpactOut,
    CycleTimeBoardOut,
    ImpactProjectionOut,
    ItemAgingOut,
    KindImpactOut,
    PartyLoadOut,
    ThreadDigestOut,
)
from app.modules.change_intelligence.service import (
    build_comms_digest_for_project,
    build_coordination_plan,
    build_impact_projection,
    build_project_board,
    clarify_change_note,
)

router = APIRouter(tags=["Change Intelligence"])


@router.get("/projects/{project_id}/cycle-time", response_model=CycleTimeBoardOut)
async def get_cycle_time_board(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> CycleTimeBoardOut:
    """Per-party "waiting on whom" board over a project's open change records."""
    await verify_project_access(project_id, user_id or "", session)

    board = await build_project_board(session, project_id)
    return CycleTimeBoardOut(
        project_id=str(project_id),
        as_of=board.as_of,
        total_open=board.total_open,
        total_overdue=board.total_overdue,
        unassigned_open=board.unassigned_open,
        parties=[PartyLoadOut.model_validate(p) for p in board.parties],
        items=[ItemAgingOut.model_validate(r) for r in board.items],
    )


@router.get("/projects/{project_id}/impact", response_model=ImpactProjectionOut)
async def get_impact_projection(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> ImpactProjectionOut:
    """Committed cost and schedule impact of a project's approved changes."""
    await verify_project_access(project_id, user_id or "", session)

    projection = await build_impact_projection(session, project_id)
    return ImpactProjectionOut(
        project_id=str(project_id),
        approved_count=projection.approved_count,
        total_schedule_delta_days=projection.total_schedule_delta_days,
        primary_currency=projection.primary_currency,
        primary_currency_cost=str(projection.primary_currency_cost),
        by_kind=[
            KindImpactOut(
                kind=k.kind,
                count=k.count,
                total_cost=str(k.total_cost),
                total_days=k.total_days,
            )
            for k in projection.by_kind
        ],
        by_currency=[
            CurrencyImpactOut(currency=c.currency, total_cost=str(c.total_cost), count=c.count)
            for c in projection.by_currency
        ],
    )


@router.post("/clarify", response_model=ClarifiedRequestOut)
async def clarify_change_request(
    payload: ClarifyIn,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> ClarifiedRequestOut:
    """Turn a rough change note into a structured, well-formed request draft.

    Stateless text analysis (no project record is read or written), so it needs
    authentication but no project-scoped access check.
    """
    clarified = clarify_change_note(payload.note, payload.contract_standard)
    return ClarifiedRequestOut.model_validate(clarified)


@router.get("/projects/{project_id}/coordination", response_model=CoordinationPlanOut)
async def get_coordination_plan(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> CoordinationPlanOut:
    """Ranked "what to act on first" plan over the project's open change items."""
    await verify_project_access(project_id, user_id or "", session)

    plan = await build_coordination_plan(session, project_id)
    return CoordinationPlanOut(
        project_id=str(project_id),
        generated_at=plan.generated_at,
        total=plan.total,
        overdue_count=plan.overdue_count,
        due_soon_count=plan.due_soon_count,
        steps=[CoordinationStepOut.model_validate(s) for s in plan.steps],
    )


@router.get("/projects/{project_id}/comms-digest", response_model=CommsDigestOut)
async def get_comms_digest(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> CommsDigestOut:
    """Open correspondence threads for the project and who owes the next reply."""
    await verify_project_access(project_id, user_id or "", session)

    digest = await build_comms_digest_for_project(session, project_id)
    return CommsDigestOut(
        project_id=str(project_id),
        generated_at=digest.generated_at,
        thread_count=digest.thread_count,
        open_count=digest.open_count,
        awaiting_us_count=digest.awaiting_us_count,
        threads=[ThreadDigestOut.model_validate(t) for t in digest.threads],
    )
