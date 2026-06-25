# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Phone-log API routes (mounted at /api/v1/phonelog).

Endpoints:
    GET  /                 - list a project's phone logs (newest first)
    POST /                 - capture a phone call / voice note / verbal instruction
    GET  /{phone_log_id}   - fetch one phone log

Authorization is project-scoped: every route runs verify_project_access against
the row's project before doing anything, which is the IDOR gate. The module does
not register fine-grained RBAC permissions - project access is the contract,
matching the value module and avoiding silent-deny from an unregistered
permission string.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import CurrentUserId, SessionDep, verify_project_access
from app.modules.phonelog import service
from app.modules.phonelog.schemas import PhoneLogCreate, PhoneLogResponse

router = APIRouter(tags=["phonelog"])
logger = logging.getLogger(__name__)


def _to_response(row: object) -> PhoneLogResponse:
    return PhoneLogResponse(
        id=row.id,  # type: ignore[attr-defined]
        project_id=row.project_id,  # type: ignore[attr-defined]
        direction=row.direction,  # type: ignore[attr-defined]
        channel=row.channel,  # type: ignore[attr-defined]
        parties=list(getattr(row, "parties", None) or []),
        occurred_at=row.occurred_at,  # type: ignore[attr-defined]
        duration_seconds=row.duration_seconds,  # type: ignore[attr-defined]
        transcript=row.transcript,  # type: ignore[attr-defined]
        summary=row.summary,  # type: ignore[attr-defined]
        instructions=list(getattr(row, "instructions", None) or []),
        word_count=row.word_count,  # type: ignore[attr-defined]
        audio_storage_key=getattr(row, "audio_storage_key", "") or "",
        status=row.status,  # type: ignore[attr-defined]
        created_by=row.created_by,  # type: ignore[attr-defined]
        metadata=getattr(row, "metadata_", {}) or {},
        created_at=row.created_at,  # type: ignore[attr-defined]
        updated_at=row.updated_at,  # type: ignore[attr-defined]
    )


@router.get("/", response_model=list[PhoneLogResponse])
async def list_phone_logs(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    direction: str | None = Query(default=None),
    channel: str | None = Query(default=None),
) -> list[PhoneLogResponse]:
    await verify_project_access(project_id, user_id, session)
    items, _ = await service.list_phone_logs(
        session,
        project_id,
        offset=offset,
        limit=limit,
        direction=direction,
        channel=channel,
    )
    return [_to_response(item) for item in items]


@router.post("/", response_model=PhoneLogResponse, status_code=201)
async def create_phone_log(
    data: PhoneLogCreate,
    user_id: CurrentUserId,
    session: SessionDep,
) -> PhoneLogResponse:
    await verify_project_access(data.project_id, user_id, session)
    row = await service.create_phone_log(session, data, user_id=user_id)
    return _to_response(row)


@router.get("/{phone_log_id}", response_model=PhoneLogResponse)
async def get_phone_log(
    phone_log_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> PhoneLogResponse:
    row = await service.get_phone_log(session, phone_log_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone log not found")
    await verify_project_access(row.project_id, str(user_id), session)
    return _to_response(row)
