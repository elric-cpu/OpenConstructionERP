# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Construction-control API routes.

Acceptance criteria:
    GET    /criteria                       - list criteria for a project
    POST   /criteria                       - create a criterion
    GET    /criteria/{criterion_id}        - get one
    PATCH  /criteria/{criterion_id}        - update
    DELETE /criteria/{criterion_id}        - delete

Inspections:
    GET    /inspections                    - list inspections for a project
    POST   /inspections                    - create an inspection (optional model link)
    GET    /inspections/{inspection_id}    - get one (with resolved element links)
    PATCH  /inspections/{inspection_id}    - update
    DELETE /inspections/{inspection_id}    - delete
    POST   /inspections/{inspection_id}/record-result - record pass/fail; a fail raises an NCR
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.construction_control.schemas import (
    AcceptanceCriterionCreate,
    AcceptanceCriterionResponse,
    AcceptanceCriterionUpdate,
    ElementRefResponse,
    InspectionCreate,
    InspectionResponse,
    InspectionResultIn,
    InspectionUpdate,
)
from app.modules.construction_control.service import ConstructionControlService

router = APIRouter(tags=["construction-control"])
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> ConstructionControlService:
    return ConstructionControlService(session)


def _criterion_response(criterion) -> AcceptanceCriterionResponse:
    return AcceptanceCriterionResponse.model_validate(criterion)


def _inspection_response(inspection, elements) -> InspectionResponse:
    resp = InspectionResponse.model_validate(inspection)
    resp.elements = [ElementRefResponse.model_validate(e) for e in elements]
    return resp


# ── Acceptance criteria ───────────────────────────────────────────────────────


@router.get("/criteria", response_model=list[AcceptanceCriterionResponse])
async def list_criteria(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    category: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    service: ConstructionControlService = Depends(_get_service),
) -> list[AcceptanceCriterionResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.list_criteria(
        project_id, offset=offset, limit=limit, category=category, is_active=is_active
    )
    return [_criterion_response(c) for c in items]


@router.post("/criteria", response_model=AcceptanceCriterionResponse, status_code=201)
async def create_criterion(
    data: AcceptanceCriterionCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("cc.criterion.create")),
    service: ConstructionControlService = Depends(_get_service),
) -> AcceptanceCriterionResponse:
    await verify_project_access(data.project_id, user_id, session)
    criterion = await service.create_criterion(data, user_id=user_id)
    return _criterion_response(criterion)


@router.get("/criteria/{criterion_id}", response_model=AcceptanceCriterionResponse)
async def get_criterion(
    criterion_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: ConstructionControlService = Depends(_get_service),
) -> AcceptanceCriterionResponse:
    criterion = await service.get_criterion(criterion_id)
    await verify_project_access(criterion.project_id, str(user_id), session)
    return _criterion_response(criterion)


@router.patch("/criteria/{criterion_id}", response_model=AcceptanceCriterionResponse)
async def update_criterion(
    criterion_id: uuid.UUID,
    data: AcceptanceCriterionUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("cc.criterion.update")),
    service: ConstructionControlService = Depends(_get_service),
) -> AcceptanceCriterionResponse:
    existing = await service.get_criterion(criterion_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    criterion = await service.update_criterion(criterion_id, data)
    return _criterion_response(criterion)


@router.delete("/criteria/{criterion_id}", status_code=204)
async def delete_criterion(
    criterion_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("cc.criterion.delete")),
    service: ConstructionControlService = Depends(_get_service),
) -> None:
    existing = await service.get_criterion(criterion_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    await service.delete_criterion(criterion_id)


# ── Inspections ───────────────────────────────────────────────────────────────


@router.get("/inspections", response_model=list[InspectionResponse])
async def list_inspections(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    type_filter: str | None = Query(default=None, alias="type"),
    status_filter: str | None = Query(default=None, alias="status"),
    party_role: str | None = Query(default=None),
    service: ConstructionControlService = Depends(_get_service),
) -> list[InspectionResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.list_inspections(
        project_id,
        offset=offset,
        limit=limit,
        inspection_type=type_filter,
        status_filter=status_filter,
        party_role=party_role,
    )
    elements_by_owner = await service.elements_for_many([i.id for i in items])
    return [_inspection_response(i, elements_by_owner.get(str(i.id), [])) for i in items]


@router.post("/inspections", response_model=InspectionResponse, status_code=201)
async def create_inspection(
    data: InspectionCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("cc.inspection.create")),
    service: ConstructionControlService = Depends(_get_service),
) -> InspectionResponse:
    await verify_project_access(data.project_id, user_id, session)
    inspection = await service.create_inspection(data, user_id=user_id)
    elements = await service.elements_for(inspection.id)
    return _inspection_response(inspection, elements)


@router.get("/inspections/{inspection_id}", response_model=InspectionResponse)
async def get_inspection(
    inspection_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: ConstructionControlService = Depends(_get_service),
) -> InspectionResponse:
    inspection = await service.get_inspection(inspection_id)
    await verify_project_access(inspection.project_id, str(user_id), session)
    elements = await service.elements_for(inspection.id)
    return _inspection_response(inspection, elements)


@router.patch("/inspections/{inspection_id}", response_model=InspectionResponse)
async def update_inspection(
    inspection_id: uuid.UUID,
    data: InspectionUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("cc.inspection.update")),
    service: ConstructionControlService = Depends(_get_service),
) -> InspectionResponse:
    existing = await service.get_inspection(inspection_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    inspection = await service.update_inspection(inspection_id, data)
    elements = await service.elements_for(inspection.id)
    return _inspection_response(inspection, elements)


@router.delete("/inspections/{inspection_id}", status_code=204)
async def delete_inspection(
    inspection_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("cc.inspection.delete")),
    service: ConstructionControlService = Depends(_get_service),
) -> None:
    existing = await service.get_inspection(inspection_id)
    await verify_project_access(existing.project_id, str(user_id), session)
    await service.delete_inspection(inspection_id)


@router.post("/inspections/{inspection_id}/record-result", response_model=InspectionResponse)
async def record_inspection_result(
    inspection_id: uuid.UUID,
    data: InspectionResultIn,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("cc.inspection.record_result")),
    service: ConstructionControlService = Depends(_get_service),
) -> InspectionResponse:
    """Record the outcome. A fail (or conditional) raises a linked NCR."""
    inspection = await service.get_inspection(inspection_id)
    await verify_project_access(inspection.project_id, user_id, session)
    inspection = await service.record_result(inspection_id, data, user_id=user_id)
    elements = await service.elements_for(inspection.id)
    return _inspection_response(inspection, elements)
