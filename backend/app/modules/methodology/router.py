# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Estimating-methodology API routes.

Mounted by the module loader at ``/api/v1/methodology``.

Every endpoint that touches project data calls
:func:`app.dependencies.verify_project_access` (which raises 404 on both
"missing" and "access denied" - the IDOR-safe policy used across the codebase)
BEFORE doing any work, and is additionally gated by an RBAC permission via
:class:`app.dependencies.RequirePermission`. The only project-agnostic endpoint
is the built-in template catalogue, which exposes no tenant data.

Endpoints:
    GET    /templates                          - List built-in templates
    POST   /templates/install                  - Install a template into a project
    GET    /?project_id=X                       - List methodologies for a project
    POST   /                                    - Create a project methodology
    GET    /active?project_id=X                 - Get a project's active methodology
    PUT    /active?project_id=X&slug=Y          - Set a project's active methodology
    GET    /{methodology_id}?project_id=X        - Get one methodology
    PATCH  /{methodology_id}?project_id=X        - Update a methodology
    DELETE /{methodology_id}?project_id=X        - Delete a methodology
    GET    /dimensions?project_id=X             - List analytical dimensions
    POST   /dimensions                          - Create an analytical dimension
    DELETE /dimensions/{dimension_id}?project_id=X - Delete a dimension
    GET    /funding-sources?project_id=X        - List funding sources
    POST   /funding-sources                     - Create a funding source
    PATCH  /funding-sources/{id}?project_id=X    - Update a funding source
    DELETE /funding-sources/{id}?project_id=X    - Delete a funding source
    POST   /compute                             - Compute the cascade for a project
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.methodology.schemas import (
    ComputeEstimateRequest,
    ComputeEstimateResponse,
    DimensionCreate,
    DimensionResponse,
    FundingSourceCreate,
    FundingSourceResponse,
    FundingSourceUpdate,
    InstallTemplateRequest,
    MethodologyCreate,
    MethodologyListItem,
    MethodologyResponse,
    MethodologyUpdate,
    TemplateListItem,
)
from app.modules.methodology.service import MethodologyService

router = APIRouter(tags=["methodology"])


def _get_service(session: SessionDep) -> MethodologyService:
    return MethodologyService(session)


# ── Built-in templates (project-agnostic catalogue) ────────────────────────


@router.get(
    "/templates",
    response_model=list[TemplateListItem],
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def list_templates() -> list[TemplateListItem]:
    """List the built-in methodology templates available for installation.

    Catalogue data only - no project or tenant information is exposed, so this
    endpoint takes no project_id and needs only the module read permission.
    """
    return [
        TemplateListItem(
            slug=tpl["slug"],
            name=tpl["name"],
            description=tpl.get("description", "") or "",
            country_code=tpl.get("country_code"),
            industry=tpl.get("industry"),
            currency=tpl.get("currency", "") or "",
            step_count=len(tpl.get("cascade_steps", [])),
        )
        for tpl in MethodologyService.list_templates()
    ]


@router.post(
    "/templates/install",
    response_model=MethodologyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("methodology.create"))],
)
async def install_template(
    payload: InstallTemplateRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> MethodologyResponse:
    """Install a built-in template into a project as an editable clone."""
    await verify_project_access(payload.project_id, user_id, session)
    obj = await service.install_template(
        project_id=payload.project_id,
        template_slug=payload.template_slug,
        idempotent=payload.idempotent,
        set_active=payload.set_active,
    )
    return MethodologyResponse.model_validate(obj)


# ── Methodology CRUD ────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[MethodologyListItem],
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def list_methodologies(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> list[MethodologyListItem]:
    """List the methodologies visible to a project (built-ins + its clones)."""
    await verify_project_access(project_id, user_id, session)
    rows = await service.list_methodologies(project_id)
    return [MethodologyListItem.model_validate(r) for r in rows]


@router.post(
    "/",
    response_model=MethodologyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("methodology.create"))],
)
async def create_methodology(
    payload: MethodologyCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> MethodologyResponse:
    """Create a project-scoped methodology."""
    await verify_project_access(payload.project_id, user_id, session)
    obj = await service.create_methodology(payload)
    return MethodologyResponse.model_validate(obj)


# ── Active methodology pointer ──────────────────────────────────────────────
# Declared before the /{methodology_id} routes so the literal path segment
# "active" is matched first and never swallowed by the UUID path parameter.


@router.get(
    "/active",
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def get_active_methodology(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> dict[str, str]:
    """Return the project's active methodology slug (international default)."""
    await verify_project_access(project_id, user_id, session)
    slug = await service.get_active_slug(project_id)
    return {"project_id": str(project_id), "methodology_slug": slug}


@router.put(
    "/active",
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def set_active_methodology(
    project_id: uuid.UUID,
    slug: str,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> dict[str, str]:
    """Set the project's active methodology (switchable per project)."""
    await verify_project_access(project_id, user_id, session)
    new_slug = await service.set_active_methodology(project_id, slug)
    return {"project_id": str(project_id), "methodology_slug": new_slug}


@router.get(
    "/{methodology_id:uuid}",
    response_model=MethodologyResponse,
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def get_methodology(
    methodology_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> MethodologyResponse:
    """Get one methodology, scoped to a project the caller can access."""
    await verify_project_access(project_id, user_id, session)
    obj = await service.get_methodology_for_project(methodology_id, project_id)
    return MethodologyResponse.model_validate(obj)


@router.patch(
    "/{methodology_id:uuid}",
    response_model=MethodologyResponse,
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def update_methodology(
    methodology_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: MethodologyUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> MethodologyResponse:
    """Update an editable, project-owned methodology."""
    await verify_project_access(project_id, user_id, session)
    obj = await service.update_methodology(methodology_id, project_id, payload)
    return MethodologyResponse.model_validate(obj)


@router.delete(
    "/{methodology_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("methodology.delete"))],
)
async def delete_methodology(
    methodology_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> None:
    """Delete an editable, project-owned methodology."""
    await verify_project_access(project_id, user_id, session)
    await service.delete_methodology(methodology_id, project_id)


# ── Analytical dimensions ────────────────────────────────────────────────────


@router.get(
    "/dimensions",
    response_model=list[DimensionResponse],
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def list_dimensions(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    methodology_slug: str | None = Query(default=None),
    service: MethodologyService = Depends(_get_service),
) -> list[DimensionResponse]:
    """List a project's analytical dimensions (optionally one methodology)."""
    await verify_project_access(project_id, user_id, session)
    rows = await service.list_dimensions(project_id, methodology_slug=methodology_slug)
    return [DimensionResponse.model_validate(r) for r in rows]


@router.post(
    "/dimensions",
    response_model=DimensionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def create_dimension(
    payload: DimensionCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> DimensionResponse:
    """Create an analytical dimension (with optional seed values)."""
    await verify_project_access(payload.project_id, user_id, session)
    obj = await service.create_dimension(payload)
    return DimensionResponse.model_validate(obj)


@router.delete(
    "/dimensions/{dimension_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def delete_dimension(
    dimension_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> None:
    """Delete a project-owned analytical dimension (values cascade)."""
    await verify_project_access(project_id, user_id, session)
    await service.delete_dimension(dimension_id, project_id)


# ── Funding sources ──────────────────────────────────────────────────────────


@router.get(
    "/funding-sources",
    response_model=list[FundingSourceResponse],
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def list_funding_sources(
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> list[FundingSourceResponse]:
    """List a project's funding-source master entries."""
    await verify_project_access(project_id, user_id, session)
    rows = await service.list_funding_sources(project_id)
    return [FundingSourceResponse.model_validate(r) for r in rows]


@router.post(
    "/funding-sources",
    response_model=FundingSourceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def create_funding_source(
    payload: FundingSourceCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> FundingSourceResponse:
    """Create a funding-source master entry for a project."""
    await verify_project_access(payload.project_id, user_id, session)
    obj = await service.create_funding_source(payload)
    return FundingSourceResponse.model_validate(obj)


@router.patch(
    "/funding-sources/{funding_source_id}",
    response_model=FundingSourceResponse,
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def update_funding_source(
    funding_source_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: FundingSourceUpdate,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> FundingSourceResponse:
    """Update a project-owned funding source."""
    await verify_project_access(project_id, user_id, session)
    obj = await service.update_funding_source(funding_source_id, project_id, payload)
    return FundingSourceResponse.model_validate(obj)


@router.delete(
    "/funding-sources/{funding_source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission("methodology.update"))],
)
async def delete_funding_source(
    funding_source_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> None:
    """Delete a project-owned funding source."""
    await verify_project_access(project_id, user_id, session)
    await service.delete_funding_source(funding_source_id, project_id)


# ── Compute estimate ─────────────────────────────────────────────────────────


@router.post(
    "/compute",
    response_model=ComputeEstimateResponse,
    dependencies=[Depends(RequirePermission("methodology.read"))],
)
async def compute_estimate(
    payload: ComputeEstimateRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    service: MethodologyService = Depends(_get_service),
) -> ComputeEstimateResponse:
    """Compute the markup cascade for a project under its active methodology.

    Resource totals come from ``resource_totals`` (caller-supplied) or are
    aggregated from ``boq_id``; ``methodology_slug`` overrides the project's
    active methodology for a what-if computation.
    """
    await verify_project_access(payload.project_id, user_id, session)
    result = await service.compute_estimate(payload)
    return ComputeEstimateResponse.model_validate(result)
