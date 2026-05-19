"""‌⁠‍Schedule Advanced API routes.

Mounted at ``/api/v1/schedule-advanced/`` by the module loader.

All write endpoints are gated by :class:`RequirePermission`. Every
project-scoped read/write/delete endpoint additionally enforces
:func:`verify_project_access` (added in v3.0.x IDOR sweep — closes the
cross-tenant exfil hole where any authenticated user could read or
mutate Last-Planner-System records belonging to another tenant's
project just by guessing UUIDs).

For nested resources (phase plans, look-aheads, constraints, weekly
plans, commitments, RNCs, baselines) the project_id is resolved by
walking the parent chain up to the owning ``MasterSchedule``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.schedule_advanced.schemas import (
    BaselineCreate,
    BaselineDeltaResponse,
    BaselineResponse,
    BaselineUpdate,
    CalendarCreate,
    CalendarResponse,
    CalendarUpdate,
    CommitmentCreate,
    CommitmentResponse,
    CommitmentUpdate,
    ConstraintCreate,
    ConstraintReadinessResponse,
    ConstraintResponse,
    ConstraintUpdate,
    CPMActivityResult,
    CPMRequest,
    CPMResponse,
    EVMRequest,
    EVMResponse,
    LookAheadCreate,
    LookAheadResponse,
    LookAheadUpdate,
    LPSDashboardResponse,
    MasterScheduleCreate,
    MasterScheduleResponse,
    MasterScheduleUpdate,
    PhasePlanCreate,
    PhasePlanResponse,
    PhasePlanUpdate,
    PPCResponse,
    RNCCreate,
    RNCParetoResponse,
    RNCParetoSortedResponse,
    RNCResponse,
    RNCUpdate,
    TIARequest,
    TIAResponse,
    WeeklyWorkPlanCreate,
    WeeklyWorkPlanResponse,
    WeeklyWorkPlanUpdate,
)
from app.modules.schedule_advanced.service import (
    ScheduleAdvancedService,
    compute_evm,
    cpm_forward_backward_pass,
    time_impact_analysis,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_service(session: SessionDep) -> ScheduleAdvancedService:
    return ScheduleAdvancedService(session)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


# ── Project-id resolvers for nested resources ─────────────────────────────


async def _project_id_for_master(
    master_id: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    master = await service.master_repo.get_by_id(master_id)
    if master is None:
        raise _not_found("MasterSchedule not found")
    return master.project_id


async def _project_id_for_phase(
    phase_id: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    phase = await service.phase_repo.get_by_id(phase_id)
    if phase is None:
        raise _not_found("PhasePlan not found")
    return await _project_id_for_master(phase.master_schedule_id, service)


async def _project_id_for_look_ahead(
    la_id: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    la = await service.look_ahead_repo.get_by_id(la_id)
    if la is None:
        raise _not_found("LookAheadPlan not found")
    return await _project_id_for_master(la.master_schedule_id, service)


async def _project_id_for_constraint(
    cid: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    c = await service.constraint_repo.get_by_id(cid)
    if c is None:
        raise _not_found("Constraint not found")
    if c.look_ahead_id is None:
        # Detached constraint — no project to verify against. Raise 404
        # rather than silently grant access (defence-in-depth).
        raise _not_found("Constraint not found")
    return await _project_id_for_look_ahead(c.look_ahead_id, service)


async def _project_id_for_weekly(
    wp_id: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    w = await service.weekly_repo.get_by_id(wp_id)
    if w is None:
        raise _not_found("WeeklyWorkPlan not found")
    return await _project_id_for_master(w.master_schedule_id, service)


async def _project_id_for_commitment(
    cid: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    c = await service.commitment_repo.get_by_id(cid)
    if c is None:
        raise _not_found("Commitment not found")
    return await _project_id_for_weekly(c.week_plan_id, service)


async def _project_id_for_rnc(
    rid: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    r = await service.rnc_repo.get_by_id(rid)
    if r is None:
        raise _not_found("RNC not found")
    return await _project_id_for_commitment(r.commitment_id, service)


async def _project_id_for_baseline(
    bid: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    b = await service.baseline_repo.get_by_id(bid)
    if b is None:
        raise _not_found("Baseline not found")
    return await _project_id_for_master(b.master_schedule_id, service)


async def _project_id_for_calendar(
    cid: uuid.UUID,
    service: ScheduleAdvancedService,
) -> uuid.UUID:
    cal = await service.calendar_repo.get_by_id(cid)
    if cal is None:
        raise _not_found("Calendar not found")
    return cal.project_id


# ── Master schedules ──────────────────────────────────────────────────────


@router.get("/master-schedules/", response_model=list[MasterScheduleResponse])
async def list_master_schedules(
    session: SessionDep,
    user_id: CurrentUserId,
    project_id: uuid.UUID = Query(...),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[MasterScheduleResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.master_repo.list_for_project(
        project_id, offset=offset, limit=limit, status=status,
    )
    return [MasterScheduleResponse.model_validate(i) for i in items]


@router.post("/master-schedules/", response_model=MasterScheduleResponse, status_code=201)
async def create_master_schedule(
    data: MasterScheduleCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> MasterScheduleResponse:
    await verify_project_access(data.project_id, user_id, session)
    m = await service.create_master_schedule(data, user_id=user_id)
    return MasterScheduleResponse.model_validate(m)


@router.get("/master-schedules/{master_id}", response_model=MasterScheduleResponse)
async def get_master_schedule(
    master_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> MasterScheduleResponse:
    project_id = await _project_id_for_master(master_id, service)
    await verify_project_access(project_id, user_id, session)
    m = await service.get_master_schedule(master_id)
    return MasterScheduleResponse.model_validate(m)


@router.patch("/master-schedules/{master_id}", response_model=MasterScheduleResponse)
async def update_master_schedule(
    master_id: uuid.UUID,
    data: MasterScheduleUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> MasterScheduleResponse:
    project_id = await _project_id_for_master(master_id, service)
    await verify_project_access(project_id, user_id, session)
    m = await service.update_master_schedule(master_id, data)
    return MasterScheduleResponse.model_validate(m)


@router.delete("/master-schedules/{master_id}", status_code=204)
async def delete_master_schedule(
    master_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_master(master_id, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_master_schedule(master_id)


@router.get("/master-schedules/{master_id}/dashboard", response_model=LPSDashboardResponse)
async def master_schedule_dashboard(
    master_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LPSDashboardResponse:
    project_id = await _project_id_for_master(master_id, service)
    await verify_project_access(project_id, user_id, session)
    m = await service.get_master_schedule(master_id)
    payload = await service.lps_dashboard_for_project(m.project_id)
    return LPSDashboardResponse(**payload)


# ── Phase plans ───────────────────────────────────────────────────────────


@router.get("/phase-plans/", response_model=list[PhasePlanResponse])
async def list_phase_plans(
    session: SessionDep,
    user_id: CurrentUserId,
    master_schedule_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[PhasePlanResponse]:
    project_id = await _project_id_for_master(master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.phase_repo.list_for_master(master_schedule_id)
    return [PhasePlanResponse.model_validate(i) for i in items]


@router.post("/phase-plans/", response_model=PhasePlanResponse, status_code=201)
async def create_phase_plan(
    data: PhasePlanCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> PhasePlanResponse:
    project_id = await _project_id_for_master(data.master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    p = await service.create_phase_plan(data)
    return PhasePlanResponse.model_validate(p)


@router.get("/phase-plans/{phase_id}", response_model=PhasePlanResponse)
async def get_phase_plan(
    phase_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> PhasePlanResponse:
    project_id = await _project_id_for_phase(phase_id, service)
    await verify_project_access(project_id, user_id, session)
    p = await service.get_phase_plan(phase_id)
    return PhasePlanResponse.model_validate(p)


@router.patch("/phase-plans/{phase_id}", response_model=PhasePlanResponse)
async def update_phase_plan(
    phase_id: uuid.UUID,
    data: PhasePlanUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> PhasePlanResponse:
    project_id = await _project_id_for_phase(phase_id, service)
    await verify_project_access(project_id, user_id, session)
    p = await service.update_phase_plan(phase_id, data)
    return PhasePlanResponse.model_validate(p)


@router.delete("/phase-plans/{phase_id}", status_code=204)
async def delete_phase_plan(
    phase_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_phase(phase_id, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_phase_plan(phase_id)


@router.post("/phase-plans/{phase_id}/pull", response_model=PhasePlanResponse)
async def pull_phase(
    phase_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.pull_phase")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> PhasePlanResponse:
    project_id = await _project_id_for_phase(phase_id, service)
    await verify_project_access(project_id, user_id, session)
    p = await service.pull_phase(phase_id, user_id=user_id)
    return PhasePlanResponse.model_validate(p)


@router.post("/phase-plans/{phase_id}/start", response_model=PhasePlanResponse)
async def start_phase(
    phase_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> PhasePlanResponse:
    project_id = await _project_id_for_phase(phase_id, service)
    await verify_project_access(project_id, user_id, session)
    p = await service.start_phase(phase_id)
    return PhasePlanResponse.model_validate(p)


@router.post("/phase-plans/{phase_id}/complete", response_model=PhasePlanResponse)
async def complete_phase(
    phase_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> PhasePlanResponse:
    project_id = await _project_id_for_phase(phase_id, service)
    await verify_project_access(project_id, user_id, session)
    p = await service.complete_phase(phase_id)
    return PhasePlanResponse.model_validate(p)


# ── Look-ahead plans ──────────────────────────────────────────────────────


@router.get("/look-aheads/", response_model=list[LookAheadResponse])
async def list_look_aheads(
    session: SessionDep,
    user_id: CurrentUserId,
    master_schedule_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[LookAheadResponse]:
    project_id = await _project_id_for_master(master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.look_ahead_repo.list_for_master(master_schedule_id)
    return [LookAheadResponse.model_validate(i) for i in items]


@router.get("/look-aheads/current", response_model=LookAheadResponse | None)
async def current_look_ahead(
    session: SessionDep,
    user_id: CurrentUserId,
    master_schedule_id: uuid.UUID = Query(...),
    today: date | None = Query(default=None),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LookAheadResponse | None:
    from datetime import UTC, datetime

    project_id = await _project_id_for_master(master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    effective = today or datetime.now(UTC).date()
    la = await service.look_ahead_repo.current_for_master(master_schedule_id, effective)
    return LookAheadResponse.model_validate(la) if la is not None else None


@router.post("/look-aheads/", response_model=LookAheadResponse, status_code=201)
async def create_look_ahead(
    data: LookAheadCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LookAheadResponse:
    project_id = await _project_id_for_master(data.master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    la = await service.create_look_ahead(data)
    return LookAheadResponse.model_validate(la)


@router.get("/look-aheads/{la_id}", response_model=LookAheadResponse)
async def get_look_ahead(
    la_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LookAheadResponse:
    project_id = await _project_id_for_look_ahead(la_id, service)
    await verify_project_access(project_id, user_id, session)
    la = await service.get_look_ahead(la_id)
    return LookAheadResponse.model_validate(la)


@router.patch("/look-aheads/{la_id}", response_model=LookAheadResponse)
async def update_look_ahead(
    la_id: uuid.UUID,
    data: LookAheadUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LookAheadResponse:
    project_id = await _project_id_for_look_ahead(la_id, service)
    await verify_project_access(project_id, user_id, session)
    la = await service.update_look_ahead(la_id, data)
    return LookAheadResponse.model_validate(la)


@router.delete("/look-aheads/{la_id}", status_code=204)
async def delete_look_ahead(
    la_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_look_ahead(la_id, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_look_ahead(la_id)


@router.post("/look-aheads/{la_id}/publish", response_model=LookAheadResponse)
async def publish_look_ahead(
    la_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LookAheadResponse:
    project_id = await _project_id_for_look_ahead(la_id, service)
    await verify_project_access(project_id, user_id, session)
    la = await service.publish_look_ahead(la_id)
    return LookAheadResponse.model_validate(la)


# ── Constraints ───────────────────────────────────────────────────────────


@router.get("/constraints/", response_model=list[ConstraintResponse])
async def list_constraints(
    session: SessionDep,
    user_id: CurrentUserId,
    look_ahead_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[ConstraintResponse]:
    project_id = await _project_id_for_look_ahead(look_ahead_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.constraint_repo.list_for_look_ahead(look_ahead_id)
    return [ConstraintResponse.model_validate(i) for i in items]


@router.post("/constraints/", response_model=ConstraintResponse, status_code=201)
async def create_constraint(
    data: ConstraintCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> ConstraintResponse:
    # ConstraintCreate may have nullable look_ahead_id — gate only if present.
    if getattr(data, "look_ahead_id", None) is not None:
        project_id = await _project_id_for_look_ahead(data.look_ahead_id, service)
        await verify_project_access(project_id, user_id, session)
    c = await service.create_constraint(data)
    return ConstraintResponse.model_validate(c)


@router.get("/constraints/{cid}", response_model=ConstraintResponse)
async def get_constraint(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> ConstraintResponse:
    project_id = await _project_id_for_constraint(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.get_constraint(cid)
    return ConstraintResponse.model_validate(c)


@router.patch("/constraints/{cid}", response_model=ConstraintResponse)
async def update_constraint(
    cid: uuid.UUID,
    data: ConstraintUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> ConstraintResponse:
    project_id = await _project_id_for_constraint(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.update_constraint(cid, data)
    return ConstraintResponse.model_validate(c)


@router.delete("/constraints/{cid}", status_code=204)
async def delete_constraint(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_constraint(cid, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_constraint(cid)


@router.post("/constraints/{cid}/clear", response_model=ConstraintResponse)
async def clear_constraint_endpoint(
    cid: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.clear_constraint")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> ConstraintResponse:
    project_id = await _project_id_for_constraint(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.clear_constraint(cid, user_id=user_id)
    return ConstraintResponse.model_validate(c)


@router.post("/constraints/{cid}/escalate", response_model=ConstraintResponse)
async def escalate_constraint_endpoint(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> ConstraintResponse:
    project_id = await _project_id_for_constraint(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.escalate_constraint(cid)
    return ConstraintResponse.model_validate(c)


@router.post("/constraints/{cid}/cannot-clear", response_model=ConstraintResponse)
async def cannot_clear_constraint_endpoint(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> ConstraintResponse:
    project_id = await _project_id_for_constraint(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.cannot_clear_constraint(cid)
    return ConstraintResponse.model_validate(c)


# ── Weekly work plans ─────────────────────────────────────────────────────


@router.get("/weekly-work-plans/", response_model=list[WeeklyWorkPlanResponse])
async def list_weekly_work_plans(
    session: SessionDep,
    user_id: CurrentUserId,
    master_schedule_id: uuid.UUID = Query(...),
    limit: int = Query(default=52, ge=1, le=520),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[WeeklyWorkPlanResponse]:
    project_id = await _project_id_for_master(master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.weekly_repo.list_for_master(master_schedule_id, limit=limit)
    return [WeeklyWorkPlanResponse.model_validate(i) for i in items]


@router.post("/weekly-work-plans/", response_model=WeeklyWorkPlanResponse, status_code=201)
async def create_weekly_work_plan(
    data: WeeklyWorkPlanCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> WeeklyWorkPlanResponse:
    project_id = await _project_id_for_master(data.master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    w = await service.create_weekly_plan(data)
    return WeeklyWorkPlanResponse.model_validate(w)


@router.get("/weekly-work-plans/{wp_id}", response_model=WeeklyWorkPlanResponse)
async def get_weekly_work_plan(
    wp_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> WeeklyWorkPlanResponse:
    project_id = await _project_id_for_weekly(wp_id, service)
    await verify_project_access(project_id, user_id, session)
    w = await service.get_weekly_plan(wp_id)
    return WeeklyWorkPlanResponse.model_validate(w)


@router.patch("/weekly-work-plans/{wp_id}", response_model=WeeklyWorkPlanResponse)
async def update_weekly_work_plan(
    wp_id: uuid.UUID,
    data: WeeklyWorkPlanUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> WeeklyWorkPlanResponse:
    project_id = await _project_id_for_weekly(wp_id, service)
    await verify_project_access(project_id, user_id, session)
    w = await service.update_weekly_plan(wp_id, data)
    return WeeklyWorkPlanResponse.model_validate(w)


@router.delete("/weekly-work-plans/{wp_id}", status_code=204)
async def delete_weekly_work_plan(
    wp_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_weekly(wp_id, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_weekly_plan(wp_id)


@router.post("/weekly-work-plans/{wp_id}/commit", response_model=WeeklyWorkPlanResponse)
async def commit_weekly_plan_endpoint(
    wp_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.commit")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> WeeklyWorkPlanResponse:
    project_id = await _project_id_for_weekly(wp_id, service)
    await verify_project_access(project_id, user_id, session)
    w = await service.commit_weekly_plan(wp_id)
    return WeeklyWorkPlanResponse.model_validate(w)


@router.post("/weekly-work-plans/{wp_id}/close", response_model=WeeklyWorkPlanResponse)
async def close_weekly_plan_endpoint(
    wp_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.close_weekly")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> WeeklyWorkPlanResponse:
    project_id = await _project_id_for_weekly(wp_id, service)
    await verify_project_access(project_id, user_id, session)
    w = await service.close_weekly_plan(wp_id)
    return WeeklyWorkPlanResponse.model_validate(w)


# ── Commitments ───────────────────────────────────────────────────────────


@router.get("/commitments/", response_model=list[CommitmentResponse])
async def list_commitments(
    session: SessionDep,
    user_id: CurrentUserId,
    week_plan_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[CommitmentResponse]:
    project_id = await _project_id_for_weekly(week_plan_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.commitment_repo.commitments_for_week(week_plan_id)
    return [CommitmentResponse.model_validate(i) for i in items]


@router.post("/commitments/", response_model=CommitmentResponse, status_code=201)
async def create_commitment(
    data: CommitmentCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CommitmentResponse:
    project_id = await _project_id_for_weekly(data.week_plan_id, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.create_commitment(data)
    return CommitmentResponse.model_validate(c)


@router.get("/commitments/{cid}", response_model=CommitmentResponse)
async def get_commitment(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CommitmentResponse:
    project_id = await _project_id_for_commitment(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.get_commitment(cid)
    return CommitmentResponse.model_validate(c)


@router.patch("/commitments/{cid}", response_model=CommitmentResponse)
async def update_commitment(
    cid: uuid.UUID,
    data: CommitmentUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CommitmentResponse:
    project_id = await _project_id_for_commitment(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.update_commitment(cid, data)
    return CommitmentResponse.model_validate(c)


@router.delete("/commitments/{cid}", status_code=204)
async def delete_commitment(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_commitment(cid, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_commitment(cid)


@router.post("/commitments/{cid}/commit", response_model=CommitmentResponse)
async def commit_commitment_endpoint(
    cid: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.commit")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CommitmentResponse:
    project_id = await _project_id_for_commitment(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.commit_to_week(cid, user_id=user_id)
    return CommitmentResponse.model_validate(c)


@router.post("/commitments/{cid}/complete", response_model=CommitmentResponse)
async def complete_commitment_endpoint(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    actual_qty: str | None = Body(default=None, embed=True),
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CommitmentResponse:
    from decimal import Decimal, InvalidOperation

    project_id = await _project_id_for_commitment(cid, service)
    await verify_project_access(project_id, user_id, session)
    qty: Decimal | None = None
    if actual_qty is not None:
        try:
            qty = Decimal(str(actual_qty))
        except (InvalidOperation, ValueError):
            qty = None
    c = await service.mark_commitment_complete(cid, actual_qty=qty)
    return CommitmentResponse.model_validate(c)


@router.post("/commitments/{cid}/miss", response_model=CommitmentResponse)
async def miss_commitment_endpoint(
    cid: uuid.UUID,
    rnc: RNCCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CommitmentResponse:
    project_id = await _project_id_for_commitment(cid, service)
    await verify_project_access(project_id, user_id, session)
    # Caller passes a full RNCCreate body — overwrite the commitment_id
    # with the URL value to ensure consistency.
    rnc_payload = rnc.model_copy(update={"commitment_id": cid})
    c, _r = await service.mark_commitment_missed(cid, rnc_payload)
    return CommitmentResponse.model_validate(c)


# ── RNCs ──────────────────────────────────────────────────────────────────


@router.get("/rncs/", response_model=list[RNCResponse])
async def list_rncs(
    session: SessionDep,
    user_id: CurrentUserId,
    commitment_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[RNCResponse]:
    project_id = await _project_id_for_commitment(commitment_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.rnc_repo.list_for_commitment(commitment_id)
    return [RNCResponse.model_validate(i) for i in items]


@router.post("/rncs/", response_model=RNCResponse, status_code=201)
async def create_rnc(
    data: RNCCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> RNCResponse:
    project_id = await _project_id_for_commitment(data.commitment_id, service)
    await verify_project_access(project_id, user_id, session)
    r = await service.create_rnc(data, user_id=user_id)
    return RNCResponse.model_validate(r)


@router.get("/rncs/pareto", response_model=RNCParetoResponse)
async def rnc_pareto_endpoint(
    session: SessionDep,
    user_id: CurrentUserId,
    project_id: uuid.UUID = Query(...),
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> RNCParetoResponse:
    await verify_project_access(project_id, user_id, session)
    counts = await service.rnc_pareto_for_project(project_id, period_start, period_end)
    return RNCParetoResponse(
        period_start=period_start,
        period_end=period_end,
        counts=counts,
        total=sum(counts.values()),
    )


@router.get("/rncs/{rid}", response_model=RNCResponse)
async def get_rnc(
    rid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> RNCResponse:
    project_id = await _project_id_for_rnc(rid, service)
    await verify_project_access(project_id, user_id, session)
    r = await service.get_rnc(rid)
    return RNCResponse.model_validate(r)


@router.patch("/rncs/{rid}", response_model=RNCResponse)
async def update_rnc(
    rid: uuid.UUID,
    data: RNCUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> RNCResponse:
    project_id = await _project_id_for_rnc(rid, service)
    await verify_project_access(project_id, user_id, session)
    r = await service.update_rnc(rid, data)
    return RNCResponse.model_validate(r)


@router.delete("/rncs/{rid}", status_code=204)
async def delete_rnc(
    rid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_rnc(rid, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_rnc(rid)


# ── Baselines ─────────────────────────────────────────────────────────────


@router.get("/baselines/", response_model=list[BaselineResponse])
async def list_baselines(
    session: SessionDep,
    user_id: CurrentUserId,
    master_schedule_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[BaselineResponse]:
    project_id = await _project_id_for_master(master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    items = await service.baseline_repo.list_for_master(master_schedule_id)
    return [BaselineResponse.model_validate(i) for i in items]


@router.post("/baselines/", response_model=BaselineResponse, status_code=201)
async def create_baseline(
    data: BaselineCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.capture_baseline")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> BaselineResponse:
    project_id = await _project_id_for_master(data.master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    b = await service.create_baseline(data, user_id=user_id)
    return BaselineResponse.model_validate(b)


@router.post("/baselines/capture", response_model=BaselineResponse, status_code=201)
async def capture_baseline_endpoint(
    data: BaselineCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("schedule_advanced.capture_baseline")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> BaselineResponse:
    project_id = await _project_id_for_master(data.master_schedule_id, service)
    await verify_project_access(project_id, user_id, session)
    b = await service.create_baseline(data, user_id=user_id)
    return BaselineResponse.model_validate(b)


@router.get("/baselines/{bid}", response_model=BaselineResponse)
async def get_baseline(
    bid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> BaselineResponse:
    project_id = await _project_id_for_baseline(bid, service)
    await verify_project_access(project_id, user_id, session)
    b = await service.get_baseline(bid)
    return BaselineResponse.model_validate(b)


@router.patch("/baselines/{bid}", response_model=BaselineResponse)
async def update_baseline(
    bid: uuid.UUID,
    data: BaselineUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> BaselineResponse:
    project_id = await _project_id_for_baseline(bid, service)
    await verify_project_access(project_id, user_id, session)
    b = await service.update_baseline(bid, data)
    return BaselineResponse.model_validate(b)


@router.delete("/baselines/{bid}", status_code=204)
async def delete_baseline(
    bid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_baseline(bid, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_baseline(bid)


@router.get("/baselines/{bid}/delta", response_model=BaselineDeltaResponse)
async def baseline_delta_endpoint(
    bid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    current_tasks: list[dict] = Body(default_factory=list),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> BaselineDeltaResponse:
    project_id = await _project_id_for_baseline(bid, service)
    await verify_project_access(project_id, user_id, session)
    return await service.compute_baseline_delta_for_schedule(bid, current_tasks)


# ── Calendars ─────────────────────────────────────────────────────────────


@router.get("/calendars/", response_model=list[CalendarResponse])
async def list_calendars(
    session: SessionDep,
    user_id: CurrentUserId,
    project_id: uuid.UUID = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[CalendarResponse]:
    await verify_project_access(project_id, user_id, session)
    items = await service.calendar_repo.list_for_project(project_id)
    return [CalendarResponse.model_validate(i) for i in items]


@router.post("/calendars/", response_model=CalendarResponse, status_code=201)
async def create_calendar(
    data: CalendarCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.create")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CalendarResponse:
    await verify_project_access(data.project_id, user_id, session)
    c = await service.create_calendar(data)
    return CalendarResponse.model_validate(c)


@router.get("/calendars/{cid}", response_model=CalendarResponse)
async def get_calendar(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CalendarResponse:
    project_id = await _project_id_for_calendar(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.get_calendar(cid)
    return CalendarResponse.model_validate(c)


@router.patch("/calendars/{cid}", response_model=CalendarResponse)
async def update_calendar(
    cid: uuid.UUID,
    data: CalendarUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.update")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> CalendarResponse:
    project_id = await _project_id_for_calendar(cid, service)
    await verify_project_access(project_id, user_id, session)
    c = await service.update_calendar(cid, data)
    return CalendarResponse.model_validate(c)


@router.delete("/calendars/{cid}", status_code=204)
async def delete_calendar(
    cid: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("schedule_advanced.delete")),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> None:
    project_id = await _project_id_for_calendar(cid, service)
    await verify_project_access(project_id, user_id, session)
    await service.delete_calendar(cid)


# ── Project-wide dashboard ────────────────────────────────────────────────


@router.get("/dashboard/project/{project_id}", response_model=LPSDashboardResponse)
async def project_dashboard(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> LPSDashboardResponse:
    await verify_project_access(project_id, user_id, session)
    payload = await service.lps_dashboard_for_project(project_id)
    return LPSDashboardResponse(**payload)


@router.get("/dashboard/project/{project_id}/ppc-trend", response_model=list[PPCResponse])
async def project_ppc_trend(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    weeks: int = Query(default=12, ge=1, le=104),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[PPCResponse]:
    await verify_project_access(project_id, user_id, session)
    recent_weekly = await service.weekly_repo.last_n_weeks_ppc(project_id, n=weeks)
    from decimal import Decimal

    return [
        PPCResponse(
            week_start_date=w.week_start_date,
            total_commitments=0,
            completed_commitments=0,
            ppc_percent=w.ppc_percent or Decimal("0"),
        )
        for w in reversed(recent_weekly)
    ]


# ── CPM / EVM / TIA — stateless analysis endpoints ────────────────────────


@router.post("/cpm", response_model=CPMResponse)
async def run_cpm(
    data: CPMRequest,
    _perm: None = Depends(RequirePermission("schedule_advanced.read")),
) -> CPMResponse:
    """‌⁠‍Run a CPM forward+backward pass on a supplied activity list.

    Stateless — no DB I/O. Useful for what-if scheduling experiments,
    importing schedules from P6/MS Project, and powering the EoT/TIA
    analytic in :mod:`app.modules.variations`.
    """
    acts = [a.model_dump() for a in data.activities]
    deps = [d.model_dump() for d in data.dependencies] if data.dependencies else None
    raw = cpm_forward_backward_pass(acts, deps)
    activities = [CPMActivityResult(**v) for v in raw.values()]
    project_finish = max((v.ef for v in activities), default=0)
    critical_count = sum(1 for v in activities if v.is_critical)
    return CPMResponse(
        project_finish_workday=project_finish,
        critical_path_count=critical_count,
        activities=activities,
    )


@router.post("/tia", response_model=TIAResponse)
async def run_tia(
    data: TIARequest,
    _perm: None = Depends(RequirePermission("schedule_advanced.read")),
) -> TIAResponse:
    """‌⁠‍Time-Impact-Analysis — recompute completion date after a delay.

    Stateless — no DB I/O. Inputs are the full schedule + a single delay
    event (impacted activity id + delay in working days). Used by the
    Variations EoT-claim workflow to drive granted-days decisions.
    """
    acts = [a.model_dump() for a in data.activities]
    deps = [d.model_dump() for d in data.dependencies] if data.dependencies else None
    result = time_impact_analysis(
        acts, deps, data.impacted_activity_id, data.delay_days,
    )
    return TIAResponse(**result)


@router.post("/evm", response_model=EVMResponse)
async def run_evm(
    data: EVMRequest,
    _perm: None = Depends(RequirePermission("schedule_advanced.read")),
) -> EVMResponse:
    """Earned Value Management — compute PV/EV/AC + SPI/CPI/EAC.

    Stateless — no DB I/O. Each activity contributes its BAC × PV-ramp
    to the project Planned Value at ``today_workday``. EV = BAC × %
    complete; AC is reported directly.
    """
    acts = [a.model_dump() for a in data.activities]
    result = compute_evm(acts, data.today_workday)
    return EVMResponse(**result)


# ── Constraint readiness + Pareto-sorted RNC ──────────────────────────────


@router.get(
    "/look-aheads/{la_id}/readiness",
    response_model=list[ConstraintReadinessResponse],
)
async def look_ahead_readiness(
    la_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    service: ScheduleAdvancedService = Depends(_get_service),
) -> list[ConstraintReadinessResponse]:
    """Return ready/not-ready summary per task for the look-ahead window."""
    project_id = await _project_id_for_look_ahead(la_id, service)
    await verify_project_access(project_id, user_id, session)
    rows = await service.look_ahead_readiness(la_id)
    return [ConstraintReadinessResponse(**r) for r in rows]


@router.get(
    "/dashboard/project/{project_id}/rnc-pareto",
    response_model=RNCParetoSortedResponse,
)
async def project_rnc_pareto_sorted(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: ScheduleAdvancedService = Depends(_get_service),
) -> RNCParetoSortedResponse:
    """Sorted-desc RNC Pareto with cumulative percentage column."""
    await verify_project_access(project_id, user_id, session)
    payload = await service.rnc_pareto_sorted_for_project(
        project_id, period_start, period_end,
    )
    return RNCParetoSortedResponse(**payload)
