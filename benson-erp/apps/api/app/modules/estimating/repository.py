import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document
from app.modules.estimating.models import Estimate, EstimateLine, Proposal


async def get_estimate(
    session: AsyncSession, tenant_id: uuid.UUID, estimate_id: uuid.UUID
) -> Estimate | None:
    return await session.scalar(
        select(Estimate).where(Estimate.tenant_id == tenant_id, Estimate.id == estimate_id)
    )


async def get_proposal(
    session: AsyncSession, tenant_id: uuid.UUID, proposal_id: uuid.UUID
) -> Proposal | None:
    return await session.scalar(
        select(Proposal).where(Proposal.tenant_id == tenant_id, Proposal.id == proposal_id)
    )


async def get_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID | None
) -> Document | None:
    if document_id is None:
        return None
    return await session.scalar(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == document_id)
    )


async def estimate_lines(
    session: AsyncSession, tenant_id: uuid.UUID, estimate_id: uuid.UUID
) -> list[EstimateLine]:
    result = await session.scalars(
        select(EstimateLine)
        .where(EstimateLine.tenant_id == tenant_id, EstimateLine.estimate_id == estimate_id)
        .order_by(EstimateLine.position)
    )
    return list(result)


async def direct_cost(session: AsyncSession, tenant_id: uuid.UUID, estimate_id: uuid.UUID):
    return await session.scalar(
        select(func.coalesce(func.sum(EstimateLine.quantity * EstimateLine.unit_cost), 0)).where(
            EstimateLine.tenant_id == tenant_id, EstimateLine.estimate_id == estimate_id
        )
    )


async def next_proposal_version(
    session: AsyncSession, tenant_id: uuid.UUID, estimate_id: uuid.UUID
) -> int:
    current = await session.scalar(
        select(func.coalesce(func.max(Proposal.document_version), 0)).where(
            Proposal.tenant_id == tenant_id, Proposal.estimate_id == estimate_id
        )
    )
    return int(current or 0) + 1
