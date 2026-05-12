# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Match Elements REST router.

Endpoints (auto-mounted at /api/v1/match_elements/ by the module loader):

    POST   /sessions                       Create session (auto-bind catalogue)
    GET    /sessions?project_id=...        List recent sessions for resume picker
    GET    /sessions/{id}                  Read one session
    PATCH  /sessions/{id}                  Update group_by / filters / archive / threshold
    POST   /sessions/{id}/touch            Bump last_active_at (cheap heartbeat)

    GET    /sessions/{id}/groups           Paginated list with summary counters
    GET    /sessions/{id}/group?group_key= Detailed group + matcher candidates
    POST   /sessions/{id}/groups/split     (Phase A.5b stub)
    POST   /sessions/{id}/groups/merge     (Phase A.5b stub)

    POST   /sessions/{id}/match            Run vector / lexical / resources matcher
    POST   /sessions/{id}/confirm          Confirm a candidate as the chosen match
    POST   /sessions/{id}/bulk-confirm     Confirm all suggested above threshold
    POST   /sessions/{id}/apply            Dry-run preview / write to BOQ
    POST   /sessions/{id}/no-match         Mark group TBD / RFQ / custom

    GET    /sessions/{id}/attributes       Drag-source list of group-by chip keys
    GET    /sessions/{id}/categories       IFC class counts (with translated labels)

    GET    /projects/{project_id}/bim-models  BIM model strip for the BIM tabs

    GET    /templates                      Tenant template library
    POST   /templates/lookup               Bulk signature lookup
    DELETE /templates/{id}                 Remove template
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.match_elements import schemas
from app.modules.match_elements.analytics import compute_match_analytics
from app.modules.match_elements.excel_import import parse_boq_xlsx
from app.modules.match_elements.models import MatchSession
from app.modules.match_elements.service import get_service

router = APIRouter()


def _u(s: str) -> uuid.UUID:
    return uuid.UUID(s)


async def _assert_session_access(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: str,
) -> uuid.UUID:
    """Authorise a request that targets a specific MatchSession.

    Loads the row, raises 404 if missing, and delegates project-level
    ownership to ``verify_project_access`` (which also returns 404 on
    deny so we don't leak existence). Returns the session's project_id
    so callers can avoid a second lookup.
    """
    row = (
        await db.execute(
            select(MatchSession.project_id).where(MatchSession.id == session_id),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Match session not found")
    project_id = row[0]
    await verify_project_access(project_id, user_id, db)
    return project_id


# ── Sessions ─────────────────────────────────────────────────────────────


@router.post("/sessions", response_model=schemas.SessionRead, status_code=201)
async def create_session(
    spec: schemas.SessionCreate,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.SessionRead:
    await verify_project_access(spec.project_id, current_user_id, session)
    try:
        return await get_service().create_session(
            session, spec, _u(current_user_id),
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/sessions/from-excel",
    response_model=schemas.SessionRead,
    status_code=201,
    summary="Create a BoQ match session by uploading an xlsx file",
)
async def create_session_from_excel(
    session: SessionDep,
    current_user_id: CurrentUserId,
    project_id: uuid.UUID = Form(...),
    file: UploadFile = File(..., description="Bill of Quantities .xlsx file"),
    name: str | None = Form(None),
    # Accepts a CWICR v3 region id ("DE_BERLIN", ...) or a legacy UUID —
    # the service layer routes each kind to its own storage slot. Was
    # ``uuid.UUID | None`` before, which 422'd every wizard submission.
    catalogue_id: str | None = Form(None),
    construction_stage: str | None = Form(None),
) -> schemas.SessionRead:
    """Upload an xlsx BoQ and create a match session in one round-trip.

    Implements MAPPING_PROCESS.md §4.1.5 — the Excel BoQ source. Column
    detection is multi-language (English/German/Russian/Spanish/Chinese
    /Japanese/Korean/Turkish/Polish/etc.); see
    :mod:`match_elements.excel_import` for the full alias table.
    Caller-side parsing is still supported via the regular
    ``POST /sessions`` endpoint with ``boq_rows`` populated — this route
    is the convenience path for end users.
    """
    await verify_project_access(project_id, current_user_id, session)

    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Only .xlsx files are supported. Save your BoQ as Excel "
                "(not .xls / .csv) and re-upload."
            ),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        rows = parse_boq_xlsx(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid BoQ rows found. Ensure your spreadsheet has a "
                "header row with at least a 'Description' column and at "
                "least one data row underneath."
            ),
        )

    spec = schemas.SessionCreate(
        project_id=project_id,
        source="boq",
        name=name or (file.filename or "BoQ Import"),
        catalogue_id=catalogue_id,
        construction_stage=construction_stage,  # type: ignore[arg-type]
        boq_rows=rows,
    )

    try:
        return await get_service().create_session(
            session, spec, _u(current_user_id),
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.get("/sessions", response_model=list[schemas.SessionSummary])
async def list_sessions(
    project_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
    include_archived: bool = False,
    limit: int = 50,
) -> list[schemas.SessionSummary]:
    await verify_project_access(project_id, current_user_id, session)
    try:
        return await get_service().list_sessions(
            session, project_id,
            include_archived=include_archived,
            limit=limit,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.get("/sessions/{session_id}", response_model=schemas.SessionRead)
async def get_session_endpoint(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.SessionRead:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().get_session(session, session_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.patch("/sessions/{session_id}", response_model=schemas.SessionRead)
async def update_session(
    session_id: uuid.UUID,
    patch: schemas.SessionUpdate,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.SessionRead:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().update_session(session, session_id, patch)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/touch", status_code=204)
async def touch_session(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> None:
    await _assert_session_access(session, session_id, current_user_id)
    await get_service().touch_session(session, session_id)


@router.get("/sessions/{session_id}/progress")
async def get_match_progress(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> dict[str, object]:
    """Lightweight progress poll for an in-flight or finished match run.

    Read-only single-row SELECT into the session's ``metadata_["progress"]``
    bag (populated by :meth:`MatchService.run_match`). The wizard's
    MatchProgressCard polls this every ~800ms while the match is
    running and stops as soon as ``status`` flips to ``done`` or
    ``error``. Always 200 — an idle session returns a neutral payload
    so the FE never has to special-case 404 vs "no run yet".
    """
    await _assert_session_access(session, session_id, current_user_id)
    return await get_service().get_progress(session, session_id)


# ── Groups ───────────────────────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/groups",
    response_model=schemas.GroupListResponse,
)
async def list_groups(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> schemas.GroupListResponse:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().list_groups(
            session, session_id, status=status, limit=limit, offset=offset,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/group",
    response_model=schemas.GroupDetail,
)
async def get_group(
    session_id: uuid.UUID,
    group_key: str,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.GroupDetail:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().get_group_detail(
            session, session_id, group_key,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/groups/split",
    response_model=schemas.GroupDetail,
)
async def split_group(
    session_id: uuid.UUID,
    group_key: str,
    spec: schemas.GroupSplitRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.GroupDetail:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().split_group(
            session, session_id, group_key, spec,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/groups/merge",
    response_model=schemas.GroupDetail,
)
async def merge_groups(
    session_id: uuid.UUID,
    group_key: str,
    spec: schemas.GroupMergeRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.GroupDetail:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().merge_groups(
            session, session_id, group_key, spec,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


# ── Attributes / categories ─────────────────────────────────────────────


@router.get(
    "/sessions/{session_id}/attributes",
    response_model=list[schemas.AttributeKey],
)
async def list_attribute_keys(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[schemas.AttributeKey]:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().list_attribute_keys(session, session_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.get(
    "/sessions/{session_id}/categories",
    response_model=list[schemas.CategoryCount],
)
async def list_categories(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[schemas.CategoryCount]:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().list_categories(session, session_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


# ── BIM models for the BIM tab strip ─────────────────────────────────────


@router.get(
    "/projects/{project_id}/bim-models",
    response_model=list[schemas.BIMModelOption],
)
async def list_project_bim_models(
    project_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[schemas.BIMModelOption]:
    """BIM models attached to a project, ready-to-bind to a session.

    Mirrors the ``/api/v1/bim_hub/`` list shape, but returns only the
    fields the match-elements page renders (filename, format, status,
    counts, timestamps). Filters out errored/processing models so the
    user can't bind to a model that has nothing to match against.
    """
    await verify_project_access(project_id, current_user_id, session)
    from app.modules.bim_hub.models import BIMModel

    stmt = (
        select(BIMModel)
        .where(BIMModel.project_id == project_id)
        .order_by(BIMModel.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[schemas.BIMModelOption] = []
    for m in rows:
        out.append(
            schemas.BIMModelOption(
                id=m.id,
                name=m.name,
                model_format=m.model_format,
                element_count=int(m.element_count or 0),
                storey_count=int(m.storey_count or 0),
                status=m.status or "",
                created_at=m.created_at,
            )
        )
    return out


# ── Match / confirm / apply ──────────────────────────────────────────────


@router.post(
    "/sessions/{session_id}/match",
    response_model=list[schemas.GroupSummary],
)
async def run_match(
    session_id: uuid.UUID,
    spec: schemas.RunMatchRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[schemas.GroupSummary]:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().run_match(session, session_id, spec)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/confirm", response_model=schemas.GroupDetail,
)
async def confirm_match(
    session_id: uuid.UUID,
    spec: schemas.ConfirmMatchRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.GroupDetail:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().confirm(
            session, session_id, spec, _u(current_user_id),
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/bulk-confirm")
async def bulk_confirm(
    session_id: uuid.UUID,
    spec: schemas.BulkConfirmRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> dict[str, int]:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        n = await get_service().bulk_confirm(
            session, session_id, spec, _u(current_user_id),
        )
        return {"confirmed_count": n}
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/apply", response_model=schemas.ApplyToBoqResponse,
)
async def apply_to_boq(
    session_id: uuid.UUID,
    spec: schemas.ApplyToBoqRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.ApplyToBoqResponse:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().apply_to_boq(
            session, session_id, spec, _u(current_user_id),
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/no-match", response_model=schemas.GroupDetail,
)
async def no_match(
    session_id: uuid.UUID,
    spec: schemas.NoMatchRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.GroupDetail:
    await _assert_session_access(session, session_id, current_user_id)
    try:
        return await get_service().no_match(session, session_id, spec)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


# ── Templates (cross-project library) ────────────────────────────────────


@router.get("/templates", response_model=list[schemas.TemplateRead])
async def list_templates(
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[schemas.TemplateRead]:
    try:
        return await get_service().list_templates(session, tenant_id=None)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/templates/lookup", response_model=schemas.TemplateLookupResponse,
)
async def lookup_templates(
    spec: schemas.TemplateLookupRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> schemas.TemplateLookupResponse:
    try:
        return await get_service().lookup_templates(
            session, tenant_id=None, signatures=spec.signatures,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> None:
    try:
        await get_service().delete_template(session, template_id)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


# ── Analytics (MAPPING_PROCESS.md §10) ───────────────────────────────────


@router.get("/analytics", response_model=schemas.AnalyticsResponse)
async def get_match_analytics(
    session: SessionDep,
    current_user_id: CurrentUserId,
    days: int = Query(7, ge=1, le=90),
    project_id: uuid.UUID | None = Query(None),
    catalog_id: str | None = Query(None, max_length=64),
) -> schemas.AnalyticsResponse:
    """Return aggregate match-quality metrics for the last ``days`` days.

    Pass ``project_id`` to scope to a single project (auth-checked the
    same way as other project routes); omit it for tenant-wide rollup
    (user must still be authenticated). ``catalog_id`` (e.g.
    ``cwicr_DE``) further narrows the window when diagnosing one
    catalogue's recall.

    Always 200 — empty windows return zero-counters with no alerts so
    the dashboard renders cleanly on a fresh deploy.
    """
    if project_id is not None:
        await verify_project_access(project_id, current_user_id, session)
    return await compute_match_analytics(
        session,
        days=days,
        project_id=project_id,
        catalog_id=catalog_id,
    )
