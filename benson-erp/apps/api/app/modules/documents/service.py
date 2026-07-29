import hashlib
import uuid
from asyncio import to_thread
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.core.storage import get_object_storage
from app.modules.crm.models import Customer, Lead, Property
from app.modules.documents.models import Document, DocumentVisibility
from app.modules.documents.proposal_pdf import render_proposal_pdf
from app.modules.estimating.models import Estimate, Proposal
from app.modules.platform.models import Organization


async def create_proposal_document(
    session: AsyncSession,
    principal: Principal,
    proposal: Proposal,
    estimate: Estimate,
) -> Document:
    lead = await session.scalar(
        select(Lead).where(Lead.tenant_id == principal.tenant_id, Lead.id == estimate.lead_id)
    )
    organization = await session.get(Organization, principal.tenant_id)
    if lead is None or lead.customer_id is None or lead.property_id is None or organization is None:
        raise HTTPException(status_code=409, detail="Proposal document context is incomplete")
    customer = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == principal.tenant_id, Customer.id == lead.customer_id
        )
    )
    property_record = await session.scalar(
        select(Property).where(
            Property.tenant_id == principal.tenant_id, Property.id == lead.property_id
        )
    )
    if customer is None or property_record is None:
        raise HTTPException(status_code=409, detail="Proposal customer or property is missing")
    context = {
        "company_name": organization.name,
        "company_phone": organization.phone,
        "primary_color": organization.primary_color,
        "proposal_number": f"{proposal.id.hex[:8].upper()}-V{proposal.document_version}",
        "customer_name": customer.display_name,
        "property_address": (
            f"{property_record.address_line_1}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
        ),
        "lines": proposal.scope_snapshot["lines"],
        **proposal.price_snapshot,
    }
    content = render_proposal_pdf(context)
    checksum = hashlib.sha256(content).hexdigest()
    filename = f'proposal-{context["proposal_number"].lower()}.pdf'
    storage_key = (
        f"tenants/{principal.tenant_id}/proposals/{proposal.id}/"
        f"v{proposal.document_version}/{checksum}.pdf"
    )
    await to_thread(
        get_object_storage().put_immutable,
        storage_key,
        content,
        "application/pdf",
    )
    document = Document(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        record_type="Proposal",
        record_id=proposal.id,
        kind="PROPOSAL",
        filename=filename,
        mime_type="application/pdf",
        storage_key=storage_key,
        checksum_sha256=checksum,
        size_bytes=len(content),
        visibility=DocumentVisibility.CLIENT,
    )
    session.add(document)
    await session.flush()
    proposal.document_id = document.id
    return document


async def get_proposal_document(
    session: AsyncSession, principal: Principal, proposal_id: uuid.UUID
) -> tuple[Document, bytes]:
    document = await get_proposal_document_record(session, principal, proposal_id)
    content = await to_thread(get_object_storage().get, document.storage_key)
    if hashlib.sha256(content).hexdigest() != document.checksum_sha256:
        raise HTTPException(status_code=409, detail="Proposal document integrity check failed")
    return document, content


async def get_proposal_document_record(
    session: AsyncSession, principal: Principal, proposal_id: uuid.UUID
) -> Document:
    principal.require("proposals.read")
    document = await session.scalar(
        select(Document).where(
            Document.tenant_id == principal.tenant_id,
            Document.record_type == "Proposal",
            Document.record_id == proposal_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Proposal document not found")
    return document


async def create_temporary_proposal_access(
    session: AsyncSession,
    principal: Principal,
    proposal_id: uuid.UUID,
    expires_seconds: int,
) -> tuple[str | None, datetime]:
    document = await get_proposal_document_record(session, principal, proposal_id)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_seconds)
    url = await to_thread(
        get_object_storage().signed_get_url,
        document.storage_key,
        expires_seconds,
    )
    return url, expires_at
