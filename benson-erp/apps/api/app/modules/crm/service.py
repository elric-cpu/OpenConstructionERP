import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.crm import repository
from app.modules.crm.models import Customer, Lead, LeadStatus, Property
from app.modules.crm.schemas import ConversionRead, LeadConvert, LeadCreate, LeadQualify
from app.modules.platform.audit import add_audit, add_outbox


def _normalize_email(email: str | None) -> str | None:
    return email.strip().lower() if email else None


def _normalize_address(address: LeadConvert) -> str:
    item = address.property
    return "|".join(
        part.strip().upper()
        for part in (item.address_line_1, item.city, item.state, item.postal_code)
    )


async def create_lead(session: AsyncSession, principal: Principal, data: LeadCreate) -> Lead:
    principal.require("leads.create")
    correlation_id = correlation_uuid()
    lead = Lead(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        **data.model_dump(),
    )
    session.add(lead)
    await session.flush()
    add_audit(
        session,
        principal,
        "Lead",
        lead.id,
        "created",
        correlation_id,
        None,
        {"status": lead.status},
    )
    add_outbox(
        session,
        principal,
        "LeadCreated",
        "Lead",
        lead.id,
        correlation_id,
        f"lead-created:{lead.id}",
        {"lead_id": str(lead.id), "source": lead.source},
    )
    await session.commit()
    return lead


async def qualify_lead(
    session: AsyncSession, principal: Principal, lead_id: uuid.UUID, data: LeadQualify
) -> Lead:
    principal.require("leads.qualify")
    lead = await repository.get_lead(session, principal.tenant_id, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if lead.version != data.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead version conflict")
    if lead.status not in {LeadStatus.NEW, LeadStatus.CONTACTED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead cannot be qualified")
    before = {"status": lead.status, "version": lead.version}
    lead.status = LeadStatus.QUALIFIED
    lead.version += 1
    lead.updated_by = principal.user_id
    add_audit(
        session,
        principal,
        "Lead",
        lead.id,
        "qualified",
        uuid.uuid4(),
        before,
        {"status": lead.status, "version": lead.version},
        data.reason,
    )
    await session.commit()
    return lead


async def convert_lead(
    session: AsyncSession, principal: Principal, lead_id: uuid.UUID, data: LeadConvert
) -> ConversionRead:
    principal.require("leads.convert")
    lead = await repository.get_lead(session, principal.tenant_id, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if lead.customer_id and lead.property_id:
        return ConversionRead(
            lead_id=lead.id, customer_id=lead.customer_id, property_id=lead.property_id
        )
    if lead.status is not LeadStatus.QUALIFIED or lead.version != data.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead is not convertible")

    normalized_email = _normalize_email(lead.email)
    customer = (
        await repository.find_customer_by_email(session, principal.tenant_id, normalized_email)
        if normalized_email
        else None
    )
    if customer is None:
        customer = Customer(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            display_name=lead.contact_name,
            email=lead.email,
            normalized_email=normalized_email,
            phone=lead.phone,
        )
        session.add(customer)
        await session.flush()

    normalized_address = _normalize_address(data)
    property_record = await repository.find_property_by_address(
        session, principal.tenant_id, normalized_address
    )
    if property_record is None:
        property_record = Property(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            customer_id=customer.id,
            normalized_address=normalized_address,
            **data.property.model_dump(),
        )
        session.add(property_record)
        await session.flush()

    lead.customer_id = customer.id
    lead.property_id = property_record.id
    lead.version += 1
    lead.updated_by = principal.user_id
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Lead",
        lead.id,
        "converted",
        correlation_id,
        None,
        {"customer_id": str(customer.id), "property_id": str(property_record.id)},
    )
    add_outbox(
        session,
        principal,
        "LeadConverted",
        "Lead",
        lead.id,
        correlation_id,
        f"lead-converted:{lead.id}",
        {"customer_id": str(customer.id), "property_id": str(property_record.id)},
    )
    await session.commit()
    return ConversionRead(lead_id=lead.id, customer_id=customer.id, property_id=property_record.id)
