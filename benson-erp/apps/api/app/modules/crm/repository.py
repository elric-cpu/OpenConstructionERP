import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Customer, Lead, Property


async def get_lead(session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
    return await session.scalar(select(Lead).where(Lead.tenant_id == tenant_id, Lead.id == lead_id))


async def find_customer_by_email(
    session: AsyncSession, tenant_id: uuid.UUID, normalized_email: str
) -> Customer | None:
    return await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.normalized_email == normalized_email
        )
    )


async def find_property_by_address(
    session: AsyncSession, tenant_id: uuid.UUID, normalized_address: str
) -> Property | None:
    return await session.scalar(
        select(Property).where(
            Property.tenant_id == tenant_id, Property.normalized_address == normalized_address
        )
    )
