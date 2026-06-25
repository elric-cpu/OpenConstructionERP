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
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.change_intelligence.schemas import (
    ChangeWatchOut,
    ClarifiedRequestOut,
    ClarifyIn,
    CommsDigestOut,
    CoordinationPlanOut,
    CoordinationStepOut,
    CurrencyExposureOut,
    CurrencyImpactOut,
    CurrencyTotalOut,
    CycleTimeBoardOut,
    DecisionImpactOut,
    DecisionImpactRowOut,
    DisputeExposureSummaryOut,
    DisputeRiskBoardOut,
    DisputeRiskItemOut,
    ImpactProjectionOut,
    ItemAgingOut,
    KindImpactOut,
    OwnershipChainOut,
    OwnershipSegmentOut,
    PartyDwellOut,
    PartyLoadOut,
    RiskFactorOut,
    ThreadDigestOut,
    WatchResultOut,
)
from app.modules.change_intelligence.service import (
    build_change_watch,
    build_comms_digest_for_project,
    build_coordination_plan,
    build_decision_impact,
    build_dispute_risk_board,
    build_impact_projection,
    build_ownership_chain_for,
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


@router.get("/changes/{kind}/{entity_id}/ownership-chain", response_model=OwnershipChainOut)
async def get_ownership_chain(
    kind: str,
    entity_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> OwnershipChainOut:
    """Reconstructed ball-in-court hand-off chain + dwell-time for one change.

    ``kind`` is the change-family token (``change_order`` / ``variation_notice``
    / ``variation_request`` / ``variation_order`` / ``moc_entry``). The record's
    project drives :func:`verify_project_access`, so the chain is only returned
    to a caller who may see the underlying change. An unknown kind or a missing
    record both 404, consistent with the rest of the project-scoped surface.
    """
    try:
        chain, project_id = await build_ownership_chain_for(session, kind, entity_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown change kind: {kind}") from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change record not found") from exc

    await verify_project_access(project_id, user_id or "", session)

    return OwnershipChainOut(
        kind=kind,
        entity_id=str(entity_id),
        project_id=str(project_id),
        as_of=chain.as_of.isoformat(),
        current_holder=chain.current_holder,
        ownership_ambiguous=chain.ownership_ambiguous,
        has_current_holder=chain.has_current_holder,
        has_unrecorded_origin=chain.has_unrecorded_origin,
        chain_inconsistent=chain.chain_inconsistent,
        unchanged_across_transition=chain.unchanged_across_transition,
        total_handoffs=chain.total_handoffs,
        ambiguity_reasons=list(chain.ambiguity_reasons),
        segments=[
            OwnershipSegmentOut(
                party=seg.party,
                from_ts=seg.from_ts.isoformat(),
                to_ts=seg.to_ts.isoformat() if seg.to_ts is not None else None,
                dwell_days=seg.dwell_days,
                is_open=seg.is_open,
                set_by=seg.set_by,
                reason=seg.reason,
            )
            for seg in chain.segments
        ],
        dwell_by_party=[
            PartyDwellOut(party=pd.party, dwell_days=pd.dwell_days, segment_count=pd.segment_count)
            for pd in chain.dwell_by_party
        ],
    )


@router.get("/projects/{project_id}/dispute-risk", response_model=DisputeRiskBoardOut)
async def get_dispute_risk_board(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> DisputeRiskBoardOut:
    """Ranked dispute-exposure radar over the project's open changes.

    Each open change is scored for how likely it is to turn into a dispute, why
    (its dominant driver), and the single most useful cure, money-weighted by
    the cost at risk. The per-currency summary never blends currencies.
    """
    await verify_project_access(project_id, user_id or "", session)

    ranked, summary = await build_dispute_risk_board(session, project_id)
    return DisputeRiskBoardOut(
        project_id=str(project_id),
        generated_at=datetime.now(UTC).isoformat(),
        items=[
            DisputeRiskItemOut(
                change_id=it.change_id,
                change_ref=it.change_ref,
                kind=it.kind,
                title=it.title,
                exposure_score=it.exposure_score,
                band=it.band,
                dominant_driver=it.dominant_driver,
                recommended_cure=it.recommended_cure,
                intrinsic_exposure=it.intrinsic_exposure,
                money_multiplier=it.money_multiplier,
                money_basis=str(it.money_basis),
                currency=it.currency,
                factors=[
                    RiskFactorOut(
                        name=f.name,
                        weight=f.weight,
                        fraction=f.fraction,
                        weighted=f.weighted,
                        is_driver=f.is_driver,
                    )
                    for f in it.factors
                ],
            )
            for it in ranked
        ],
        summary=DisputeExposureSummaryOut(
            item_count=summary.item_count,
            band_counts=summary.band_counts,
            by_currency=[
                CurrencyExposureOut(
                    currency=c.currency,
                    item_count=c.item_count,
                    money_basis_total=str(c.money_basis_total),
                    exposure_weighted_amount=str(c.exposure_weighted_amount),
                )
                for c in summary.by_currency
            ],
            top_driver_counts=summary.top_driver_counts,
        ),
    )


@router.get("/decision-impact", response_model=DecisionImpactOut)
async def get_decision_impact(
    project_id: uuid.UUID,
    candidate_change_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> DecisionImpactOut:
    """Preview what approving one candidate change adds to the committed baseline.

    Gathers the project's committed change-order and variation-order impacts as
    the baseline, resolves the candidate change by id from any change-family
    table, and returns the before / after position per (kind, currency) plus a
    per-currency rollup. Every money / day figure is a string and currencies are
    never blended. A candidate id not found in the project 404s.
    """
    await verify_project_access(project_id, user_id or "", session)

    try:
        impact, candidate = await build_decision_impact(session, project_id, candidate_change_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate change not found") from exc

    return DecisionImpactOut(
        project_id=str(project_id),
        candidate_change_id=str(candidate_change_id),
        candidate_kind=candidate.kind,
        candidate_currency=candidate.currency,
        rows=[
            DecisionImpactRowOut(
                kind=r.kind,
                currency=r.currency,
                current_committed_cost=str(r.current_committed_cost),
                candidate_cost_delta=str(r.candidate_cost_delta),
                resulting_cost=str(r.resulting_cost),
                current_committed_days=str(r.current_committed_days),
                candidate_days_delta=str(r.candidate_days_delta),
                resulting_days=str(r.resulting_days),
            )
            for r in impact.rows
        ],
        totals_by_currency=[
            CurrencyTotalOut(
                currency=t.currency,
                current_committed_cost=str(t.current_committed_cost),
                candidate_cost_delta=str(t.candidate_cost_delta),
                resulting_cost=str(t.resulting_cost),
                current_committed_days=str(t.current_committed_days),
                candidate_days_delta=str(t.candidate_days_delta),
                resulting_days=str(t.resulting_days),
            )
            for t in impact.totals_by_currency
        ],
    )


@router.get("/projects/{project_id}/change-watch", response_model=ChangeWatchOut)
async def get_change_watch(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> ChangeWatchOut:
    """Proactive watch: which open changes are quietly drifting toward trouble.

    Classifies each change as stalled / incomplete / lost (or ok) from its age,
    movement and ownership, worst-first, with a per-class count.
    """
    await verify_project_access(project_id, user_id or "", session)

    watch = await build_change_watch(session, project_id)
    return ChangeWatchOut(
        project_id=str(project_id),
        generated_at=datetime.now(UTC).isoformat(),
        item_count=watch.item_count,
        counts=watch.counts,
        items=[
            WatchResultOut(
                change_id=r.change_id,
                kind=r.kind,
                classification=r.classification,
                reasons=list(r.reasons),
                idle_days=r.idle_days,
                overdue_days=r.overdue_days,
            )
            for r in watch.items
        ],
    )
