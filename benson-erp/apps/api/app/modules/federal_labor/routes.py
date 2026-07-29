import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.federal_labor import service
from app.modules.federal_labor.schemas import (
    EmployeeQualificationCreate,
    EmployeeQualificationRead,
    FederalChargeCodeClose,
    FederalChargeCodeCreate,
    FederalChargeCodeRead,
    FederalInvoicePreview,
    FederalInvoiceSupportRead,
    FederalInvoiceSupportRequest,
    FederalLaborRateCreate,
    FederalLaborRateRead,
    FloorCheckReport,
)

router = APIRouter(prefix="/federal-labor", tags=["federal-labor"])


@router.post(
    "/charge-codes",
    response_model=FederalChargeCodeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_charge_code(
    data: FederalChargeCodeCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FederalChargeCodeRead:
    return FederalChargeCodeRead.model_validate(
        await service.create_charge_code(session, principal, data)
    )


@router.get("/charge-codes", response_model=list[FederalChargeCodeRead])
async def list_charge_codes(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[FederalChargeCodeRead]:
    return [
        FederalChargeCodeRead.model_validate(item)
        for item in await service.list_charge_codes(session, principal)
    ]


@router.post(
    "/charge-codes/{charge_code_id}/close",
    response_model=FederalChargeCodeRead,
)
async def close_charge_code(
    charge_code_id: uuid.UUID,
    data: FederalChargeCodeClose,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FederalChargeCodeRead:
    return FederalChargeCodeRead.model_validate(
        await service.close_charge_code(
            session,
            principal,
            charge_code_id,
            expected_version,
            data,
        )
    )


@router.post(
    "/rates",
    response_model=FederalLaborRateRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_rate(
    data: FederalLaborRateCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FederalLaborRateRead:
    return FederalLaborRateRead.model_validate(
        await service.create_rate(session, principal, data)
    )


@router.get("/rates", response_model=list[FederalLaborRateRead])
async def list_rates(
    charge_code_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[FederalLaborRateRead]:
    return [
        FederalLaborRateRead.model_validate(item)
        for item in await service.list_rates(session, principal, charge_code_id)
    ]


@router.post(
    "/qualifications",
    response_model=EmployeeQualificationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_qualification(
    data: EmployeeQualificationCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeQualificationRead:
    return EmployeeQualificationRead.model_validate(
        await service.create_qualification(session, principal, data)
    )


@router.get("/qualifications", response_model=list[EmployeeQualificationRead])
async def list_qualifications(
    employee_id: uuid.UUID | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[EmployeeQualificationRead]:
    return [
        EmployeeQualificationRead.model_validate(item)
        for item in await service.list_qualifications(
            session,
            principal,
            employee_id,
        )
    ]


@router.get("/floor-check", response_model=FloorCheckReport)
async def get_floor_check(
    period_start: date = Query(),
    period_end: date = Query(),
    contract_code: str | None = Query(default=None, min_length=1, max_length=100),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FloorCheckReport:
    return await service.floor_check(
        session,
        principal,
        period_start,
        period_end,
        contract_code,
    )


@router.post("/invoice-support/preview", response_model=FederalInvoicePreview)
async def preview_invoice_support(
    data: FederalInvoiceSupportRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FederalInvoicePreview:
    return await service.preview_invoice_support(session, principal, data)


@router.post(
    "/invoice-support",
    response_model=FederalInvoiceSupportRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_invoice_support(
    data: FederalInvoiceSupportRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FederalInvoiceSupportRead:
    return await service.generate_invoice_support(session, principal, data)


@router.get("/invoice-support", response_model=list[FederalInvoiceSupportRead])
async def list_invoice_support(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[FederalInvoiceSupportRead]:
    return await service.list_invoice_support(session, principal)


@router.get(
    "/invoice-support/{support_id}",
    response_model=FederalInvoiceSupportRead,
)
async def get_invoice_support(
    support_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> FederalInvoiceSupportRead:
    return await service.get_invoice_support(session, principal, support_id)
