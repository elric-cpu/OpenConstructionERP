"""Carbon & Sustainability API routes.

Mounted at ``/api/v1/carbon/``.

Endpoints:
    GET    /epd                          - List EPD records
    POST   /epd                          - Create EPD record
    GET    /epd/{id}                     - Get single EPD
    PATCH  /epd/{id}                     - Update EPD
    DELETE /epd/{id}                     - Delete EPD
    POST   /epd/sync                     - Trigger external EPD sync hook
    GET    /material-factors             - List material factors
    POST   /material-factors             - Create factor
    GET    /material-factors/{id}        - Get factor
    PATCH  /material-factors/{id}        - Update factor
    DELETE /material-factors/{id}        - Delete factor
    GET    /inventories                  - List inventories for a project
    POST   /inventories                  - Create inventory
    GET    /inventories/{id}             - Get inventory
    PATCH  /inventories/{id}             - Update inventory
    DELETE /inventories/{id}             - Delete inventory
    POST   /inventories/{id}/finalize    - Mark as baseline/current
    GET    /inventories/{id}/totals      - Compute fresh totals
    GET    /inventories/{id}/alternatives - Alternative-material picker
    GET    /inventories/{id}/embodied    - List embodied entries
    POST   /inventories/{id}/embodied    - Create embodied entry
    POST   /inventories/{id}/embodied/bulk - Bulk-create embodied entries
    PATCH  /embodied/{id}                - Update entry
    DELETE /embodied/{id}                - Delete entry
    GET    /inventories/{id}/scope1      - List scope-1 entries
    POST   /scope1                       - Create scope-1 entry
    PATCH  /scope1/{id}                  - Update scope-1 entry
    DELETE /scope1/{id}                  - Delete scope-1 entry
    GET    /inventories/{id}/scope2      - List scope-2 entries
    POST   /scope2                       - Create scope-2 entry
    PATCH  /scope2/{id}                  - Update scope-2 entry
    DELETE /scope2/{id}                  - Delete scope-2 entry
    GET    /inventories/{id}/scope3      - List scope-3 entries
    POST   /scope3                       - Create scope-3 entry
    PATCH  /scope3/{id}                  - Update scope-3 entry
    DELETE /scope3/{id}                  - Delete scope-3 entry
    GET    /targets?project_id=          - List targets
    POST   /targets                      - Create target
    PATCH  /targets/{id}                 - Update target
    DELETE /targets/{id}                 - Delete target
    GET    /targets/{id}/progress        - Target progress snapshot
    GET    /reports?project_id=          - List reports
    POST   /reports                      - Create report record (manual)
    PATCH  /reports/{id}                 - Update report
    DELETE /reports/{id}                 - Delete report
    POST   /reports/generate             - Generate report from inventory
    GET    /dashboard?project_id=        - Project carbon dashboard
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import CurrentUserId, RequirePermission, SessionDep, verify_project_access
from app.modules.carbon.schemas import (
    AlternativeComparisonResponse,
    AlternativeMaterialOption,
    CarbonDashboardResponse,
    CarbonInventoryCreate,
    CarbonInventoryResponse,
    CarbonInventoryUpdate,
    CarbonTargetCreate,
    CarbonTargetResponse,
    CarbonTargetUpdate,
    EmbodiedBulkCreate,
    EmbodiedCarbonEntryCreate,
    EmbodiedCarbonEntryResponse,
    EmbodiedCarbonEntryUpdate,
    EPDRecordCreate,
    EPDRecordResponse,
    EPDRecordUpdate,
    InventoryTotalsResponse,
    MaterialCarbonFactorCreate,
    MaterialCarbonFactorResponse,
    MaterialCarbonFactorUpdate,
    Scope1EntryCreate,
    Scope1EntryResponse,
    Scope1EntryUpdate,
    Scope2EntryCreate,
    Scope2EntryResponse,
    Scope2EntryUpdate,
    Scope3EntryCreate,
    Scope3EntryResponse,
    Scope3EntryUpdate,
    SustainabilityReportCreate,
    SustainabilityReportPayload,
    SustainabilityReportResponse,
    SustainabilityReportUpdate,
    TargetProgressResponse,
)
from app.modules.carbon.service import CarbonService

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> CarbonService:
    return CarbonService(session)


# ── EPD records ──────────────────────────────────────────────────────────


@router.get("/epd", response_model=list[EPDRecordResponse])
async def list_epd(
    material_class: str | None = Query(default=None),
    region: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[EPDRecordResponse]:
    items, _ = await service.list_epds(
        material_class=material_class, region=region, offset=offset, limit=limit,
    )
    return [EPDRecordResponse.model_validate(i) for i in items]


@router.post("/epd", response_model=EPDRecordResponse, status_code=201)
async def create_epd(
    data: EPDRecordCreate,
    _perm: None = Depends(RequirePermission("carbon.import_epd")),
    service: CarbonService = Depends(_get_service),
) -> EPDRecordResponse:
    epd = await service.create_epd(data)
    return EPDRecordResponse.model_validate(epd)


@router.post("/epd/sync")
async def sync_epd(
    source: str = Query(default="oekobaudat"),
    region: str | None = Query(default=None),
    _perm: None = Depends(RequirePermission("carbon.import_epd")),
    service: CarbonService = Depends(_get_service),
) -> dict[str, int | str]:
    count = await service.sync_epds_from_external(source=source, region=region)
    return {"source": source, "imported": count}


@router.get("/epd/{epd_id}", response_model=EPDRecordResponse)
async def get_epd(
    epd_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> EPDRecordResponse:
    epd = await service.get_epd(epd_id)
    return EPDRecordResponse.model_validate(epd)


@router.patch("/epd/{epd_id}", response_model=EPDRecordResponse)
async def update_epd(
    epd_id: uuid.UUID,
    data: EPDRecordUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> EPDRecordResponse:
    epd = await service.update_epd(epd_id, data)
    return EPDRecordResponse.model_validate(epd)


@router.delete("/epd/{epd_id}", status_code=204)
async def delete_epd(
    epd_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_epd(epd_id)


# ── Material factors ─────────────────────────────────────────────────────


@router.get("/material-factors", response_model=list[MaterialCarbonFactorResponse])
async def list_factors(
    cost_item_id: uuid.UUID | None = Query(default=None),
    region: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[MaterialCarbonFactorResponse]:
    items, _ = await service.list_factors(
        cost_item_id=cost_item_id, region=region, offset=offset, limit=limit,
    )
    return [MaterialCarbonFactorResponse.model_validate(i) for i in items]


@router.post("/material-factors", response_model=MaterialCarbonFactorResponse, status_code=201)
async def create_factor(
    data: MaterialCarbonFactorCreate,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> MaterialCarbonFactorResponse:
    factor = await service.create_factor(data)
    return MaterialCarbonFactorResponse.model_validate(factor)


@router.get("/material-factors/{factor_id}", response_model=MaterialCarbonFactorResponse)
async def get_factor(
    factor_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> MaterialCarbonFactorResponse:
    factor = await service.get_factor(factor_id)
    return MaterialCarbonFactorResponse.model_validate(factor)


@router.patch("/material-factors/{factor_id}", response_model=MaterialCarbonFactorResponse)
async def update_factor(
    factor_id: uuid.UUID,
    data: MaterialCarbonFactorUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> MaterialCarbonFactorResponse:
    factor = await service.update_factor(factor_id, data)
    return MaterialCarbonFactorResponse.model_validate(factor)


@router.delete("/material-factors/{factor_id}", status_code=204)
async def delete_factor(
    factor_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_factor(factor_id)


# ── Inventories ──────────────────────────────────────────────────────────


@router.get("/inventories", response_model=list[CarbonInventoryResponse])
async def list_inventories(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: CarbonService = Depends(_get_service),
) -> list[CarbonInventoryResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.list_inventories(project_id, offset=offset, limit=limit)
    return [CarbonInventoryResponse.model_validate(i) for i in items]


@router.post("/inventories", response_model=CarbonInventoryResponse, status_code=201)
async def create_inventory(
    data: CarbonInventoryCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> CarbonInventoryResponse:
    await verify_project_access(data.project_id, user_id, session)
    inv = await service.create_inventory(data, user_id=user_id)
    return CarbonInventoryResponse.model_validate(inv)


@router.get("/inventories/{inventory_id}", response_model=CarbonInventoryResponse)
async def get_inventory(
    inventory_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> CarbonInventoryResponse:
    inv = await service.get_inventory(inventory_id)
    return CarbonInventoryResponse.model_validate(inv)


@router.patch("/inventories/{inventory_id}", response_model=CarbonInventoryResponse)
async def update_inventory(
    inventory_id: uuid.UUID,
    data: CarbonInventoryUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> CarbonInventoryResponse:
    inv = await service.update_inventory(inventory_id, data)
    return CarbonInventoryResponse.model_validate(inv)


@router.delete("/inventories/{inventory_id}", status_code=204)
async def delete_inventory(
    inventory_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_inventory(inventory_id)


@router.post("/inventories/{inventory_id}/finalize", response_model=CarbonInventoryResponse)
async def finalize_inventory(
    inventory_id: uuid.UUID,
    status_value: str = Query(default="baseline", pattern=r"^(baseline|current)$"),
    _perm: None = Depends(RequirePermission("carbon.finalize_inventory")),
    service: CarbonService = Depends(_get_service),
) -> CarbonInventoryResponse:
    inv = await service.finalize_inventory(inventory_id, status_value=status_value)
    return CarbonInventoryResponse.model_validate(inv)


@router.get("/inventories/{inventory_id}/totals", response_model=InventoryTotalsResponse)
async def inventory_totals(
    inventory_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> InventoryTotalsResponse:
    totals = await service.compute_inventory_totals_fresh(inventory_id)
    return InventoryTotalsResponse(
        inventory_id=inventory_id,
        embodied_a1a3=totals.get("embodied_a1a3", "0"),
        embodied_a4=totals.get("embodied_a4", "0"),
        embodied_a5=totals.get("embodied_a5", "0"),
        embodied_a1a5=totals.get("embodied_a1a5", "0"),
        embodied_b=totals.get("embodied_b", "0"),
        embodied_c=totals.get("embodied_c", "0"),
        embodied_d=totals.get("embodied_d", "0"),
        scope1=totals.get("scope1", "0"),
        scope2=totals.get("scope2", "0"),
        scope3=totals.get("scope3", "0"),
        operational=totals.get("operational", "0"),
        end_of_life=totals.get("end_of_life", "0"),
        total=totals.get("total", "0"),
    )


@router.get(
    "/inventories/{inventory_id}/alternatives",
    response_model=AlternativeComparisonResponse,
)
async def inventory_alternatives(
    inventory_id: uuid.UUID,
    entry_id: uuid.UUID = Query(...),
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> AlternativeComparisonResponse:
    # inventory_id kept for clarity / URL stability; entry already constrains it
    _ = inventory_id
    payload = await service.alternatives_for_entry(entry_id)
    options = [AlternativeMaterialOption(**opt) for opt in payload["options"]]
    return AlternativeComparisonResponse(
        entry_id=payload["entry_id"],
        current_factor_value=payload["current_factor_value"],
        current_carbon_kg=payload["current_carbon_kg"],
        options=options,
    )


# ── Embodied entries ─────────────────────────────────────────────────────


@router.get(
    "/inventories/{inventory_id}/embodied",
    response_model=list[EmbodiedCarbonEntryResponse],
)
async def list_embodied(
    inventory_id: uuid.UUID,
    stage: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[EmbodiedCarbonEntryResponse]:
    items, _ = await service.list_embodied_entries(
        inventory_id, stage=stage, offset=offset, limit=limit,
    )
    return [EmbodiedCarbonEntryResponse.model_validate(i) for i in items]


@router.post(
    "/inventories/{inventory_id}/embodied",
    response_model=EmbodiedCarbonEntryResponse,
    status_code=201,
)
async def create_embodied(
    inventory_id: uuid.UUID,
    data: EmbodiedCarbonEntryCreate,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> EmbodiedCarbonEntryResponse:
    if data.inventory_id != inventory_id:
        data = data.model_copy(update={"inventory_id": inventory_id})
    entry = await service.create_embodied_entry(data)
    return EmbodiedCarbonEntryResponse.model_validate(entry)


@router.post(
    "/inventories/{inventory_id}/embodied/bulk",
    status_code=201,
)
async def bulk_create_embodied(
    inventory_id: uuid.UUID,
    body: EmbodiedBulkCreate,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> dict[str, int | str]:
    entries = [
        e.model_copy(update={"inventory_id": inventory_id}) for e in body.entries
    ]
    n = await service.bulk_create_embodied(inventory_id, entries)
    return {"inventory_id": str(inventory_id), "created": n}


@router.patch("/embodied/{entry_id}", response_model=EmbodiedCarbonEntryResponse)
async def update_embodied(
    entry_id: uuid.UUID,
    data: EmbodiedCarbonEntryUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> EmbodiedCarbonEntryResponse:
    entry = await service.update_embodied_entry(entry_id, data)
    return EmbodiedCarbonEntryResponse.model_validate(entry)


@router.delete("/embodied/{entry_id}", status_code=204)
async def delete_embodied(
    entry_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_embodied_entry(entry_id)


# ── Scope 1 ──────────────────────────────────────────────────────────────


@router.get("/inventories/{inventory_id}/scope1", response_model=list[Scope1EntryResponse])
async def list_scope1(
    inventory_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[Scope1EntryResponse]:
    items, _ = await service.list_scope1(inventory_id)
    return [Scope1EntryResponse.model_validate(i) for i in items]


@router.post("/scope1", response_model=Scope1EntryResponse, status_code=201)
async def create_scope1(
    data: Scope1EntryCreate,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> Scope1EntryResponse:
    entry = await service.create_scope1(data)
    return Scope1EntryResponse.model_validate(entry)


@router.patch("/scope1/{entry_id}", response_model=Scope1EntryResponse)
async def update_scope1(
    entry_id: uuid.UUID,
    data: Scope1EntryUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> Scope1EntryResponse:
    entry = await service.update_scope1(entry_id, data)
    return Scope1EntryResponse.model_validate(entry)


@router.delete("/scope1/{entry_id}", status_code=204)
async def delete_scope1(
    entry_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_scope1(entry_id)


# ── Scope 2 ──────────────────────────────────────────────────────────────


@router.get("/inventories/{inventory_id}/scope2", response_model=list[Scope2EntryResponse])
async def list_scope2(
    inventory_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[Scope2EntryResponse]:
    items, _ = await service.list_scope2(inventory_id)
    return [Scope2EntryResponse.model_validate(i) for i in items]


@router.post("/scope2", response_model=Scope2EntryResponse, status_code=201)
async def create_scope2(
    data: Scope2EntryCreate,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> Scope2EntryResponse:
    entry = await service.create_scope2(data)
    return Scope2EntryResponse.model_validate(entry)


@router.patch("/scope2/{entry_id}", response_model=Scope2EntryResponse)
async def update_scope2(
    entry_id: uuid.UUID,
    data: Scope2EntryUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> Scope2EntryResponse:
    entry = await service.update_scope2(entry_id, data)
    return Scope2EntryResponse.model_validate(entry)


@router.delete("/scope2/{entry_id}", status_code=204)
async def delete_scope2(
    entry_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_scope2(entry_id)


# ── Scope 3 ──────────────────────────────────────────────────────────────


@router.get("/inventories/{inventory_id}/scope3", response_model=list[Scope3EntryResponse])
async def list_scope3(
    inventory_id: uuid.UUID,
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[Scope3EntryResponse]:
    items, _ = await service.list_scope3(inventory_id)
    return [Scope3EntryResponse.model_validate(i) for i in items]


@router.post("/scope3", response_model=Scope3EntryResponse, status_code=201)
async def create_scope3(
    data: Scope3EntryCreate,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> Scope3EntryResponse:
    entry = await service.create_scope3(data)
    return Scope3EntryResponse.model_validate(entry)


@router.patch("/scope3/{entry_id}", response_model=Scope3EntryResponse)
async def update_scope3(
    entry_id: uuid.UUID,
    data: Scope3EntryUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> Scope3EntryResponse:
    entry = await service.update_scope3(entry_id, data)
    return Scope3EntryResponse.model_validate(entry)


@router.delete("/scope3/{entry_id}", status_code=204)
async def delete_scope3(
    entry_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_scope3(entry_id)


# ── Targets ──────────────────────────────────────────────────────────────


@router.get("/targets", response_model=list[CarbonTargetResponse])
async def list_targets(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[CarbonTargetResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.list_targets(project_id)
    return [CarbonTargetResponse.model_validate(i) for i in items]


@router.post("/targets", response_model=CarbonTargetResponse, status_code=201)
async def create_target(
    data: CarbonTargetCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("carbon.set_targets")),
    service: CarbonService = Depends(_get_service),
) -> CarbonTargetResponse:
    await verify_project_access(data.project_id, user_id, session)
    target = await service.create_target(data, user_id=user_id)
    return CarbonTargetResponse.model_validate(target)


@router.patch("/targets/{target_id}", response_model=CarbonTargetResponse)
async def update_target(
    target_id: uuid.UUID,
    data: CarbonTargetUpdate,
    _perm: None = Depends(RequirePermission("carbon.set_targets")),
    service: CarbonService = Depends(_get_service),
) -> CarbonTargetResponse:
    target = await service.update_target(target_id, data)
    return CarbonTargetResponse.model_validate(target)


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(
    target_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_target(target_id)


@router.get("/targets/{target_id}/progress", response_model=TargetProgressResponse)
async def target_progress(
    target_id: uuid.UUID,
    as_of_date: date | None = Query(default=None),
    _user: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> TargetProgressResponse:
    payload = await service.target_progress(target_id, as_of_date=as_of_date)
    return TargetProgressResponse(**payload)


# ── Reports ──────────────────────────────────────────────────────────────


@router.get("/reports", response_model=list[SustainabilityReportResponse])
async def list_reports(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> list[SustainabilityReportResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.list_reports(project_id)
    return [SustainabilityReportResponse.model_validate(i) for i in items]


@router.post("/reports", response_model=SustainabilityReportResponse, status_code=201)
async def create_report(
    data: SustainabilityReportCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("carbon.generate_report")),
    service: CarbonService = Depends(_get_service),
) -> SustainabilityReportResponse:
    await verify_project_access(data.project_id, user_id, session)
    report = await service.create_report_record(data, user_id=user_id)
    return SustainabilityReportResponse.model_validate(report)


@router.patch("/reports/{report_id}", response_model=SustainabilityReportResponse)
async def update_report(
    report_id: uuid.UUID,
    data: SustainabilityReportUpdate,
    _perm: None = Depends(RequirePermission("carbon.update")),
    service: CarbonService = Depends(_get_service),
) -> SustainabilityReportResponse:
    report = await service.update_report(report_id, data)
    return SustainabilityReportResponse.model_validate(report)


@router.delete("/reports/{report_id}", status_code=204)
async def delete_report(
    report_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("carbon.delete")),
    service: CarbonService = Depends(_get_service),
) -> None:
    await service.delete_report(report_id)


@router.post("/reports/generate", response_model=SustainabilityReportResponse, status_code=201)
async def generate_report(
    payload: SustainabilityReportPayload,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("carbon.generate_report")),
    service: CarbonService = Depends(_get_service),
) -> SustainabilityReportResponse:
    await verify_project_access(payload.project_id, user_id, session)
    report = await service.generate_report(payload, user_id=user_id)
    return SustainabilityReportResponse.model_validate(report)


# ── Dashboard ────────────────────────────────────────────────────────────


@router.get("/dashboard", response_model=CarbonDashboardResponse)
async def project_dashboard(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    service: CarbonService = Depends(_get_service),
) -> CarbonDashboardResponse:
    await verify_project_access(project_id, user_id, session)
    payload = await service.project_dashboard(project_id)
    return CarbonDashboardResponse(**payload)


# ── EPD ingestion by identifier ──────────────────────────────────────────


@router.post("/epd/ingest")
async def ingest_epd_by_identifier(
    payload: dict,
    _perm: None = Depends(RequirePermission("carbon.import_epd")),
    service: CarbonService = Depends(_get_service),
) -> dict:
    """Ingest an EPD record by parsing a public-database identifier or URL.

    Body:
        identifier: str — e.g. "oekobaudat:1.4.01.04" or a URL.
        gwp_a1a3: required, the GWP-100 value.
        product_name, material_class: required identification.
        manufacturer, region, declared_unit, validity_until, document_url: optional.
    """
    identifier = payload.get("identifier")
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="identifier is required",
        )
    gwp = payload.get("gwp_a1a3")
    if gwp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="gwp_a1a3 is required",
        )
    product_name = payload.get("product_name") or ""
    material_class = payload.get("material_class") or ""
    if not product_name or not material_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_name and material_class are required",
        )
    try:
        record = await service.ingest_epd_by_identifier(
            identifier=identifier,
            gwp_a1a3=gwp,
            product_name=product_name,
            material_class=material_class,
            manufacturer=payload.get("manufacturer"),
            region=payload.get("region", ""),
            declared_unit=payload.get("declared_unit", "kg"),
            validity_until=payload.get("validity_until"),
            document_url=payload.get("document_url"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    return {
        "id": str(record.id),
        "epd_id": record.epd_id,
        "source": record.source,
        "material_class": record.material_class,
        "gwp_a1a3": str(record.gwp_a1a3),
    }


# ── Grid factor lookup ───────────────────────────────────────────────────


@router.get("/grid-factor")
async def lookup_grid_factor(
    country_code: str = Query(..., min_length=2, max_length=8),
    year: int = Query(..., ge=2000, le=2100),
    _perm: None = Depends(RequirePermission("carbon.read")),
    service: CarbonService = Depends(_get_service),
) -> dict:
    """Look up the grid emission factor (kg CO2e / kWh) for (country, year).

    Falls back to the nearest year ≤ requested for the same country.
    """
    return service.lookup_grid_factor(country_code, year)


# ── BOQ position → carbon assignment ─────────────────────────────────────


@router.post("/inventories/{inventory_id}/assign-boq-position")
async def assign_boq_position(
    inventory_id: uuid.UUID,
    payload: dict,
    _perm: None = Depends(RequirePermission("carbon.create")),
    service: CarbonService = Depends(_get_service),
) -> dict:
    """Create an embodied-carbon entry tied to a BOQ position.

    Body:
        boq_position_id: uuid, required.
        material_factor_id: uuid, required.
        quantity: number, required.
        quantity_unit: str, required ("kg" | "m3" | "m2" | "t" | "pcs" | "m").
        stage: EN 15978 stage (default "a1a3").
        density_kg_per_m3: optional, needed for m3 ↔ kg conversion.
    """
    try:
        boq_position_id = uuid.UUID(str(payload["boq_position_id"]))
        material_factor_id = uuid.UUID(str(payload["material_factor_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {exc}",
        ) from exc
    quantity = payload.get("quantity")
    quantity_unit = payload.get("quantity_unit") or ""
    if quantity is None or not quantity_unit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="quantity and quantity_unit are required",
        )
    stage = payload.get("stage") or "a1a3"
    density = payload.get("density_kg_per_m3")
    entry = await service.assign_boq_position_carbon(
        inventory_id=inventory_id,
        boq_position_id=boq_position_id,
        material_factor_id=material_factor_id,
        quantity=quantity,
        quantity_unit=quantity_unit,
        stage=stage,
        density_kg_per_m3=density,
    )
    return {
        "id": str(entry.id),
        "inventory_id": str(entry.inventory_id),
        "element_ref": entry.element_ref,
        "stage": entry.stage,
        "carbon_kg": str(entry.carbon_kg),
    }


# ── TCFD / ISSB structured report ────────────────────────────────────────


@router.post("/reports/tcfd")
async def generate_tcfd_report(
    payload: dict,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("carbon.generate_report")),
    service: CarbonService = Depends(_get_service),
) -> dict:
    """Generate a TCFD / ISSB-aligned sustainability report.

    Body:
        project_id: uuid, required.
        inventory_id: uuid, optional — when omitted, uses the latest
            baseline/current inventory.
        period_start / period_end: ISO date strings, optional.
        gross_floor_area_m2 / net_internal_area_m2 / revenue_million: optional
            denominators for intensity metrics.
        narrative: dict[section → text] for each of governance / strategy /
            risk_management / metrics_and_targets.
        project_name: optional display name.
    """
    try:
        project_id = uuid.UUID(str(payload["project_id"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id is required and must be a UUID",
        ) from exc
    await verify_project_access(project_id, user_id, session)
    inventory_id_raw = payload.get("inventory_id")
    inventory_id: uuid.UUID | None = None
    if inventory_id_raw is not None:
        try:
            inventory_id = uuid.UUID(str(inventory_id_raw))
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid inventory_id: {exc}",
            ) from exc
    narrative = payload.get("narrative")
    if narrative is not None and not isinstance(narrative, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="narrative must be a dict[section → text]",
        )
    report = await service.generate_tcfd_report(
        project_id,
        inventory_id=inventory_id,
        period_start=str(payload.get("period_start") or ""),
        period_end=str(payload.get("period_end") or ""),
        gross_floor_area_m2=payload.get("gross_floor_area_m2"),
        net_internal_area_m2=payload.get("net_internal_area_m2"),
        revenue_million=payload.get("revenue_million"),
        narrative=narrative,
        project_name=str(payload.get("project_name") or ""),
        user_id=user_id,
    )
    return {
        "id": str(report.id),
        "project_id": str(report.project_id),
        "framework": report.framework,
        "period_start": str(report.period_start),
        "period_end": str(report.period_end),
        "totals": report.totals,
    }
