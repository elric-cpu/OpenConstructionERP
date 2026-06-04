# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll API routes (mounted at ``/api/v1/payroll``).

Endpoints (all manager-scoped + project-access checked):
    POST  /projects/{project_id}/batches/        - generate a draft batch
    GET   /projects/{project_id}/batches/        - list batches for a project
    GET   /batches/{batch_id}                     - batch detail with entries
    PATCH /batches/{batch_id}/finalize/           - approve + post labour cost
    GET   /projects/{project_id}/labour-cost/     - live labour-cost rollup
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.payroll.schemas import (
    LabourCostResponse,
    PayrollBatchDetailResponse,
    PayrollBatchGenerate,
    PayrollBatchResponse,
    PayrollEntryResponse,
)
from app.modules.payroll.service import PayrollService

router = APIRouter(tags=["payroll"])


def _get_service(session: SessionDep) -> PayrollService:
    return PayrollService(session)


@router.post(
    "/projects/{project_id}/batches/",
    response_model=PayrollBatchDetailResponse,
    status_code=201,
    dependencies=[Depends(RequirePermission("payroll.manage"))],
)
async def generate_batch(
    project_id: uuid.UUID,
    data: PayrollBatchGenerate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Generate a draft payroll batch by aggregating field labour."""
    await verify_project_access(project_id, user_id, session)
    batch, entries = await service.generate_batch(
        project_id,
        date_from=data.date_from,
        date_to=data.date_to,
        period_label=data.period_label,
        notes=data.notes,
        user_id=user_id,
    )
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.get(
    "/projects/{project_id}/batches/",
    response_model=list[PayrollBatchResponse],
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def list_batches(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PayrollService = Depends(_get_service),
) -> list[PayrollBatchResponse]:
    """List payroll batches for a project (most recent first)."""
    await verify_project_access(project_id, user_id, session)
    batches, _ = await service.list_batches(project_id, offset=offset, limit=limit)
    return [PayrollBatchResponse.model_validate(b) for b in batches]


@router.get(
    "/batches/{batch_id}",
    response_model=PayrollBatchDetailResponse,
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def get_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Get a payroll batch and its entries."""
    batch = await service.get_batch(batch_id)
    # IDOR guard: the batch's project must be one the caller can access.
    await verify_project_access(batch.project_id, user_id, session)
    entries = await service.list_entries(batch_id)
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.patch(
    "/batches/{batch_id}/finalize/",
    response_model=PayrollBatchDetailResponse,
    dependencies=[Depends(RequirePermission("payroll.finalize"))],
)
async def finalize_batch(
    batch_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: PayrollService = Depends(_get_service),
) -> PayrollBatchDetailResponse:
    """Approve a draft batch and post its labour cost to the project budget.

    Idempotent: a second call on an already-approved batch returns 200 with the
    unchanged batch. The labour cost lands on the project's cost-spine labour
    budget line (never double-posted). 404 if the batch is missing, 400 if it is
    in a status that cannot be finalized.
    """
    batch = await service.get_batch(batch_id)
    # IDOR guard: the caller must have access to the batch's project.
    await verify_project_access(batch.project_id, user_id, session)
    batch = await service.finalize_batch(batch_id)
    entries = await service.list_entries(batch_id)
    detail = PayrollBatchDetailResponse.model_validate(batch)
    detail.entries = [PayrollEntryResponse.model_validate(e) for e in entries]
    return detail


@router.get(
    "/projects/{project_id}/labour-cost/",
    response_model=LabourCostResponse,
    dependencies=[Depends(RequirePermission("payroll.read"))],
)
async def get_labour_cost(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    date_from: str | None = Query(default=None, max_length=20),
    date_to: str | None = Query(default=None, max_length=20),
    service: PayrollService = Depends(_get_service),
) -> LabourCostResponse:
    """Live labour-cost rollup (base currency) - surfaced beside the cost model."""
    await verify_project_access(project_id, user_id, session)
    cost, hours, currency = await service.labour_cost(project_id, date_from=date_from, date_to=date_to)
    return LabourCostResponse(
        project_id=project_id,
        currency=currency,
        labour_cost=str(cost),
        total_hours=str(hours),
    )
