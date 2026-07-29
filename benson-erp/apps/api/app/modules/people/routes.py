import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_principal
from app.core.tenancy import get_tenant_session
from app.modules.people import service
from app.modules.people.schemas import (
    EmployeeActivationPreview,
    EmployeeActivationRead,
    EmployeeActivationReissue,
    EmployeeApproval,
    EmployeeApprovalRead,
    EmployeeCreate,
    EmployeeRead,
    IdentityProvisioningRead,
)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    data: EmployeeCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeRead:
    return EmployeeRead.model_validate(await service.create_employee(session, principal, data))


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> list[EmployeeRead]:
    employees = await service.list_employees(session, principal)
    return [EmployeeRead.model_validate(employee) for employee in employees]


@router.get("/me", response_model=EmployeeRead)
async def get_own_employee(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeRead:
    return EmployeeRead.model_validate(await service.get_own_employee(session, principal))


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    employee_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeRead:
    return EmployeeRead.model_validate(
        await service.get_employee(session, principal, employee_id)
    )


@router.post("/{employee_id}/approve", response_model=EmployeeApprovalRead)
async def approve_employee(
    employee_id: uuid.UUID,
    data: EmployeeApproval,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeApprovalRead:
    return await service.approve_employee(
        session,
        principal,
        employee_id,
        expected_version,
        data,
    )


@router.get(
    "/{employee_id}/provisioning",
    response_model=IdentityProvisioningRead,
)
async def get_employee_provisioning(
    employee_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> IdentityProvisioningRead:
    return IdentityProvisioningRead.model_validate(
        await service.get_employee_provisioning(session, principal, employee_id)
    )


@router.post(
    "/{employee_id}/activation/reissue",
    response_model=EmployeeActivationRead,
)
async def reissue_employee_activation(
    employee_id: uuid.UUID,
    data: EmployeeActivationReissue,
    expected_version: int = Header(alias="If-Match", ge=1),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeActivationRead:
    return await service.reissue_employee_activation(
        session, principal, employee_id, expected_version, data
    )


@router.get(
    "/{employee_id}/activation-preview",
    response_model=EmployeeActivationPreview,
    include_in_schema=False,
)
async def get_employee_activation_preview(
    employee_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
) -> EmployeeActivationPreview:
    return await service.get_employee_activation_preview(session, principal, employee_id)
