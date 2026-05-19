# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Clash detection API routes — mounted by the loader at ``/api/v1/clash``.

Endpoints
    GET    /projects/{project_id}/models                 → models picker
    GET    /projects/{project_id}/runs/                   → list runs
    POST   /projects/{project_id}/runs/                   → create + execute
    GET    /projects/{project_id}/runs/{run_id}           → run + matrix
    DELETE /projects/{project_id}/runs/{run_id}
    GET    /projects/{project_id}/runs/{run_id}/results   → paginated results
    PATCH  /projects/{project_id}/runs/{run_id}/results/{result_id}
    POST   /projects/{project_id}/runs/{run_id}/export-bcf

Auth mirrors the ``bcf`` module exactly: a coarse ``RequirePermission``
gate plus a per-project owner/admin IDOR check so a viewer of one
project can never read another project's clashes.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserId, RequirePermission, SessionDep
from app.modules.clash.schemas import (
    ClashBCFExportRequest,
    ClashBCFExportResponse,
    ClashCategoriesResponse,
    ClashCategoryItem,
    ClashResultPage,
    ClashResultResponse,
    ClashResultUpdate,
    ClashRunCreate,
    ClashRunListItem,
    ClashRunResponse,
)
from app.modules.clash.service import ClashService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Clash Detection"])


def _get_service(session: SessionDep) -> ClashService:
    return ClashService(session)


async def _require_project_access(
    session: AsyncSession, project_id: uuid.UUID, user_id: str
) -> None:
    """‌⁠‍Verify the caller owns (or is admin on) ``project_id`` (IDOR guard)."""
    from app.modules.projects.repository import ProjectRepository
    from app.modules.users.repository import UserRepository

    project = await ProjectRepository(session).get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    try:
        user = await UserRepository(session).get_by_id(uuid.UUID(str(user_id)))
        if user is not None and getattr(user, "role", "") == "admin":
            return
    except Exception:  # noqa: BLE001 — best-effort admin check
        logger.exception("Admin-role lookup failed during clash access check")
    if str(getattr(project, "owner_id", "")) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: you do not own this project",
        )


@router.get(
    "/projects/{project_id}/models",
    dependencies=[Depends(RequirePermission("clash.read"))],
)
async def list_models(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> list[dict]:
    """‌⁠‍Lightweight BIM-model list for the run-config picker."""
    await _require_project_access(session, project_id, user_id)
    models = await service.repo.models_for_project(project_id)
    return [
        {
            "id": str(m.id),
            "name": getattr(m, "name", None) or getattr(m, "filename", "Model"),
            "element_count": int(getattr(m, "element_count", 0) or 0),
            "status": getattr(m, "status", None),
        }
        for m in models
    ]


@router.get(
    "/projects/{project_id}/categories",
    response_model=ClashCategoriesResponse,
    dependencies=[Depends(RequirePermission("clash.read"))],
)
async def list_categories(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
    model_ids: list[uuid.UUID] = Query(default_factory=list),
) -> ClashCategoriesResponse:
    """Distinct element_type / discipline facets for the Set A/B pickers.

    Scoped to the project (IDOR-guarded); ``model_ids`` are intersected
    with the project's own models so a caller can never enumerate
    another project's element taxonomy.
    """
    await _require_project_access(session, project_id, user_id)
    project_models = {
        m.id for m in await service.repo.models_for_project(project_id)
    }
    wanted = [m for m in model_ids if m in project_models] or list(
        project_models
    )
    etypes, discs = await service.repo.categories_for_models(wanted)
    return ClashCategoriesResponse(
        element_types=[
            ClashCategoryItem(value=v, count=n) for v, n in etypes
        ],
        disciplines=[
            ClashCategoryItem(value=v, count=n) for v, n in discs
        ],
    )


@router.get(
    "/projects/{project_id}/runs/",
    response_model=list[ClashRunListItem],
    dependencies=[Depends(RequirePermission("clash.read"))],
)
async def list_runs(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> list[ClashRunListItem]:
    await _require_project_access(session, project_id, user_id)
    runs = await service.list_runs(project_id)
    return [ClashRunListItem.model_validate(r) for r in runs]


@router.post(
    "/projects/{project_id}/runs/",
    response_model=ClashRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("clash.create"))],
)
async def create_run(
    project_id: uuid.UUID,
    data: ClashRunCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> ClashRunResponse:
    await _require_project_access(session, project_id, user_id)
    run = await service.create_run(project_id, data, user_id)
    return ClashRunResponse.model_validate(run)


@router.get(
    "/projects/{project_id}/runs/{run_id}",
    response_model=ClashRunResponse,
    dependencies=[Depends(RequirePermission("clash.read"))],
)
async def get_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> ClashRunResponse:
    await _require_project_access(session, project_id, user_id)
    run = await service.get_run(project_id, run_id)
    return ClashRunResponse.model_validate(run)


@router.delete(
    "/projects/{project_id}/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("clash.delete"))],
)
async def delete_run(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> None:
    await _require_project_access(session, project_id, user_id)
    await service.delete_run(project_id, run_id)


@router.get(
    "/projects/{project_id}/runs/{run_id}/results",
    response_model=ClashResultPage,
    dependencies=[Depends(RequirePermission("clash.read"))],
)
async def list_results(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
    status_filter: str | None = Query(default=None, alias="status"),
    clash_type: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ClashResultPage:
    await _require_project_access(session, project_id, user_id)
    await service.get_run(project_id, run_id)  # 404 if run not in project
    rows, total = await service.list_results(
        run_id,
        status=status_filter,
        clash_type=clash_type,
        discipline=discipline,
        offset=offset,
        limit=limit,
    )
    return ClashResultPage(
        items=[ClashResultResponse.model_validate(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/projects/{project_id}/runs/{run_id}/results/{result_id}",
    response_model=ClashResultResponse,
    dependencies=[Depends(RequirePermission("clash.update"))],
)
async def update_result(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    result_id: uuid.UUID,
    data: ClashResultUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> ClashResultResponse:
    await _require_project_access(session, project_id, user_id)
    result = await service.update_result(
        project_id,
        run_id,
        result_id,
        new_status=data.status,
        assigned_to=data.assigned_to,
    )
    return ClashResultResponse.model_validate(result)


@router.post(
    "/projects/{project_id}/runs/{run_id}/export-bcf",
    response_model=ClashBCFExportResponse,
    dependencies=[Depends(RequirePermission("clash.export"))],
)
async def export_bcf(
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    data: ClashBCFExportRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: ClashService = Depends(_get_service),
) -> ClashBCFExportResponse:
    await _require_project_access(session, project_id, user_id)
    exported, skipped = await service.export_bcf(
        project_id, run_id, data, author=user_id, user_id=user_id
    )
    return ClashBCFExportResponse(exported=exported, skipped=skipped)
