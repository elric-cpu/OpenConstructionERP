import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.crm import service
from app.modules.crm.schemas import ConversionRead, LeadConvert, LeadCreate, LeadQualify, LeadRead

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: LeadCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadRead:
    return LeadRead.model_validate(await service.create_lead(session, principal, data))


@router.post("/{lead_id}/qualify", response_model=LeadRead)
async def qualify_lead(
    lead_id: uuid.UUID,
    data: LeadQualify,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> LeadRead:
    return LeadRead.model_validate(await service.qualify_lead(session, principal, lead_id, data))


@router.post("/{lead_id}/convert", response_model=ConversionRead)
async def convert_lead(
    lead_id: uuid.UUID,
    data: LeadConvert,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> ConversionRead:
    return await service.convert_lead(session, principal, lead_id, data)
