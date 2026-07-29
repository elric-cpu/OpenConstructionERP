import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.crm.models import Lead, LeadStatus
from app.modules.documents.models import Document
from app.modules.documents.service import create_proposal_document
from app.modules.estimating import repository
from app.modules.estimating.calculations import calculate_totals
from app.modules.estimating.models import (
    Estimate,
    EstimateLine,
    EstimateSection,
    EstimateStatus,
    Proposal,
    ProposalStatus,
)
from app.modules.estimating.schemas import EstimateCreate, EstimateLineCreate, ProposalAccept
from app.modules.platform.audit import add_audit, add_outbox


async def create_estimate(
    session: AsyncSession, principal: Principal, data: EstimateCreate
) -> Estimate:
    principal.require("estimates.create")
    lead = await session.scalar(
        select(Lead).where(Lead.tenant_id == principal.tenant_id, Lead.id == data.lead_id)
    )
    if lead is None or lead.property_id is None:
        raise HTTPException(status_code=409, detail="Lead must be converted before estimating")
    estimate = Estimate(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        lead_id=lead.id,
        property_id=lead.property_id,
        pricing_mode=data.pricing_mode,
        pricing_rate=data.pricing_rate,
        tax_rate=data.tax_rate,
    )
    lead.status = LeadStatus.ESTIMATE_IN_PROGRESS
    lead.updated_by = principal.user_id
    lead.version += 1
    session.add(estimate)
    await session.flush()
    add_audit(
        session,
        principal,
        "Estimate",
        estimate.id,
        "created",
        uuid.uuid4(),
        None,
        {"status": estimate.status},
    )
    await session.commit()
    return estimate


async def add_line(
    session: AsyncSession, principal: Principal, estimate_id: uuid.UUID, data: EstimateLineCreate
) -> Estimate:
    principal.require("estimates.write")
    estimate = await repository.get_estimate(session, principal.tenant_id, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if estimate.status is not EstimateStatus.DRAFT or estimate.version != data.expected_version:
        raise HTTPException(status_code=409, detail="Estimate is immutable or stale")
    section = await session.scalar(
        select(EstimateSection).where(
            EstimateSection.tenant_id == principal.tenant_id,
            EstimateSection.estimate_id == estimate.id,
            EstimateSection.title == data.section_title,
        )
    )
    if section is None:
        section = EstimateSection(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            estimate_id=estimate.id,
            title=data.section_title,
            position=data.position,
        )
        session.add(section)
        await session.flush()
    session.add(
        EstimateLine(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            estimate_id=estimate.id,
            section_id=section.id,
            description=data.description,
            quantity=data.quantity,
            unit=data.unit,
            unit_cost=data.unit_cost,
            category=data.category,
            position=data.position,
        )
    )
    await session.flush()
    cost = Decimal(await repository.direct_cost(session, principal.tenant_id, estimate.id))
    totals = calculate_totals(cost, estimate.pricing_mode, estimate.pricing_rate, estimate.tax_rate)
    estimate.direct_cost, estimate.selling_price = totals.direct_cost, totals.selling_price
    estimate.tax, estimate.total = totals.tax, totals.total
    estimate.version += 1
    estimate.updated_by = principal.user_id
    await session.commit()
    return estimate


async def approve_estimate(
    session: AsyncSession, principal: Principal, estimate_id: uuid.UUID, expected_version: int
) -> Estimate:
    principal.require("estimates.approve")
    estimate = await repository.get_estimate(session, principal.tenant_id, estimate_id)
    lines = await repository.estimate_lines(session, principal.tenant_id, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if estimate.version != expected_version or estimate.status is not EstimateStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Estimate is immutable or stale")
    if not lines:
        raise HTTPException(status_code=409, detail="Estimate has no line items")
    estimate.status = EstimateStatus.APPROVED
    estimate.approved_at = datetime.now(UTC)
    estimate.version += 1
    estimate.updated_by = principal.user_id
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Estimate",
        estimate.id,
        "approved",
        correlation_id,
        None,
        {"total": str(estimate.total)},
    )
    add_outbox(
        session,
        principal,
        "EstimateApproved",
        "Estimate",
        estimate.id,
        correlation_id,
        f"estimate-approved:{estimate.id}:{estimate.version}",
        {"total": str(estimate.total)},
    )
    await session.commit()
    return estimate


async def create_proposal(
    session: AsyncSession, principal: Principal, estimate_id: uuid.UUID
) -> tuple[Proposal, Document]:
    principal.require("proposals.create")
    estimate = await repository.get_estimate(session, principal.tenant_id, estimate_id)
    if estimate is None or estimate.status is not EstimateStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Approved estimate required")
    lines = await repository.estimate_lines(session, principal.tenant_id, estimate.id)
    proposal = Proposal(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        estimate_id=estimate.id,
        document_version=await repository.next_proposal_version(
            session, principal.tenant_id, estimate.id
        ),
        status=ProposalStatus.SENT,
        scope_snapshot={
            "lines": [
                {"description": line.description, "quantity": str(line.quantity), "unit": line.unit}
                for line in lines
            ]
        },
        price_snapshot={
            "selling_price": str(estimate.selling_price),
            "tax": str(estimate.tax),
            "total": str(estimate.total),
        },
    )
    session.add(proposal)
    await session.flush()
    document = await create_proposal_document(session, principal, proposal, estimate)
    add_audit(
        session,
        principal,
        "Document",
        document.id,
        "generated",
        uuid.uuid4(),
        None,
        {"checksum_sha256": document.checksum_sha256, "proposal_id": str(proposal.id)},
    )
    await session.commit()
    return proposal, document


async def accept_proposal(
    session: AsyncSession,
    principal: Principal,
    proposal_id: uuid.UUID,
    data: ProposalAccept,
    ip: str | None,
    user_agent: str | None,
) -> Proposal:
    principal.require("proposals.accept")
    proposal = await repository.get_proposal(session, principal.tenant_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status is ProposalStatus.ACCEPTED:
        return proposal
    if proposal.version != data.expected_version or proposal.status is not ProposalStatus.SENT:
        raise HTTPException(status_code=409, detail="Proposal cannot be accepted")
    if not data.consent:
        raise HTTPException(status_code=422, detail="Acceptance consent is required")
    document = await repository.get_document(
        session, principal.tenant_id, proposal.document_id
    )
    if document is None:
        raise HTTPException(status_code=409, detail="Proposal document is unavailable")
    proposal.status = ProposalStatus.ACCEPTED
    proposal.accepted_at = datetime.now(UTC)
    proposal.accepted_by_name = data.accepted_by_name
    proposal.acceptance_ip = ip
    proposal.acceptance_user_agent = user_agent
    proposal.acceptance_statement = data.acceptance_statement
    proposal.accepted_document_checksum = document.checksum_sha256
    proposal.version += 1
    proposal.updated_by = principal.user_id
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Proposal",
        proposal.id,
        "accepted",
        correlation_id,
        None,
        {
            "accepted_by": data.accepted_by_name,
            "document_checksum": document.checksum_sha256,
        },
    )
    add_outbox(
        session,
        principal,
        "ProposalAccepted",
        "Proposal",
        proposal.id,
        correlation_id,
        f"proposal-accepted:{proposal.id}",
        {"proposal_id": str(proposal.id)},
    )
    await session.commit()
    return proposal
