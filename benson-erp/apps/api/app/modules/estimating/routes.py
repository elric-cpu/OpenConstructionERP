import uuid

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.documents import service as document_service
from app.modules.estimating import service
from app.modules.estimating.schemas import (
    EstimateCreate,
    EstimateLineCreate,
    EstimateRead,
    ProposalAccept,
    ProposalDocumentAccess,
    ProposalRead,
)

router = APIRouter(tags=["estimating"])


@router.post("/estimates", response_model=EstimateRead, status_code=status.HTTP_201_CREATED)
async def create_estimate(
    data: EstimateCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EstimateRead:
    return EstimateRead.model_validate(await service.create_estimate(session, principal, data))


@router.post("/estimates/{estimate_id}/lines", response_model=EstimateRead)
async def add_line(
    estimate_id: uuid.UUID,
    data: EstimateLineCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EstimateRead:
    return EstimateRead.model_validate(
        await service.add_line(session, principal, estimate_id, data)
    )


@router.post("/estimates/{estimate_id}/approve", response_model=EstimateRead)
async def approve_estimate(
    estimate_id: uuid.UUID,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EstimateRead:
    return EstimateRead.model_validate(
        await service.approve_estimate(session, principal, estimate_id, expected_version)
    )


@router.post("/estimates/{estimate_id}/proposals", response_model=ProposalRead)
async def create_proposal(
    estimate_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProposalRead:
    proposal, document = await service.create_proposal(session, principal, estimate_id)
    result = ProposalRead.model_validate(proposal)
    return result.model_copy(update={"document_checksum": document.checksum_sha256})


@router.get("/proposals/{proposal_id}/document")
async def download_proposal_document(
    proposal_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> Response:
    document, content = await document_service.get_proposal_document(
        session, principal, proposal_id
    )
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.filename}"',
            "ETag": f'"{document.checksum_sha256}"',
            "Cache-Control": "private, immutable, max-age=31536000",
        },
    )


@router.post(
    "/proposals/{proposal_id}/document-access",
    response_model=ProposalDocumentAccess,
)
async def create_proposal_document_access(
    proposal_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProposalDocumentAccess:
    url, expires_at = await document_service.create_temporary_proposal_access(
        session,
        principal,
        proposal_id,
        settings.storage_signed_url_seconds,
    )
    return ProposalDocumentAccess(
        url=url,
        expires_at=expires_at,
        proxied=url is None,
    )


@router.post("/proposals/{proposal_id}/accept", response_model=ProposalRead)
async def accept_proposal(
    request: Request,
    proposal_id: uuid.UUID,
    data: ProposalAccept,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ProposalRead:
    client_ip = request.client.host if request.client else None
    return ProposalRead.model_validate(
        await service.accept_proposal(
            session,
            principal,
            proposal_id,
            data,
            client_ip,
            request.headers.get("user-agent"),
        )
    )
