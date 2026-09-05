import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.people.models import (
    Employee,
    EmployeeActivationRequest,
    IdentityProvisioningRequest,
)


async def get_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Employee | None:
    statement = select(Employee).where(
        Employee.tenant_id == tenant_id,
        Employee.id == employee_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def list_employees(session: AsyncSession, tenant_id: uuid.UUID) -> list[Employee]:
    return list(
        await session.scalars(
            select(Employee)
            .where(Employee.tenant_id == tenant_id)
            .order_by(Employee.last_name, Employee.first_name)
        )
    )


async def get_employee_by_user(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Employee | None:
    return await session.scalar(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.user_id == user_id,
        )
    )


async def get_provisioning_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> IdentityProvisioningRequest | None:
    return await session.scalar(
        select(IdentityProvisioningRequest).where(
            IdentityProvisioningRequest.tenant_id == tenant_id,
            IdentityProvisioningRequest.id == request_id,
        )
    )


async def get_employee_provisioning_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> IdentityProvisioningRequest | None:
    return await session.scalar(
        select(IdentityProvisioningRequest).where(
            IdentityProvisioningRequest.tenant_id == tenant_id,
            IdentityProvisioningRequest.employee_id == employee_id,
        )
    )


async def get_activation_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> EmployeeActivationRequest | None:
    statement = select(EmployeeActivationRequest).where(
        EmployeeActivationRequest.tenant_id == tenant_id,
        EmployeeActivationRequest.id == request_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def get_activation_request_by_token_hash(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    token_hash: str,
    *,
    for_update: bool = False,
) -> EmployeeActivationRequest | None:
    statement = select(EmployeeActivationRequest).where(
        EmployeeActivationRequest.tenant_id == tenant_id,
        EmployeeActivationRequest.token_hash == token_hash,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def get_active_activation_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    *,
    at: datetime | None = None,
    for_update: bool = False,
) -> EmployeeActivationRequest | None:
    statement = (
        select(EmployeeActivationRequest)
        .where(
            EmployeeActivationRequest.tenant_id == tenant_id,
            EmployeeActivationRequest.employee_id == employee_id,
            EmployeeActivationRequest.used_at.is_(None),
            EmployeeActivationRequest.revoked_at.is_(None),
            EmployeeActivationRequest.expires_at > (at or datetime.now(UTC)),
        )
        .order_by(EmployeeActivationRequest.created_at.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)
