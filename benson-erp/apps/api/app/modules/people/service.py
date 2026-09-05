import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.people import repository
from app.modules.people.audit import employee_audit_state
from app.modules.people.events import (
    EMPLOYEE_ACTIVATION_REQUESTED,
    EMPLOYEE_ACTIVATION_REVOKED,
    EMPLOYEE_CREATED,
    EMPLOYEE_PROVISIONING_REQUESTED,
)
from app.modules.people.models import (
    Employee,
    EmployeeActivationRequest,
    EmployeeStatus,
    IdentityProvisioningRequest,
)
from app.modules.people.permissions import (
    EMPLOYEES_APPROVE,
    EMPLOYEES_MANAGE,
    require_employee_activation,
)
from app.modules.people.schemas import (
    EmployeeActivationPreview,
    EmployeeActivationRead,
    EmployeeActivationReissue,
    EmployeeApproval,
    EmployeeApprovalRead,
    EmployeeCreate,
)
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.platform.models import Organization

DOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


async def create_employee(
    session: AsyncSession,
    principal: Principal,
    data: EmployeeCreate,
) -> Employee:
    principal.require(EMPLOYEES_MANAGE)
    employee = Employee(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        **data.model_dump(mode="python"),
    )
    session.add(employee)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Employee",
        employee.id,
        "created",
        correlation_id,
        None,
        employee_audit_state(employee),
    )
    add_outbox(
        session,
        principal,
        EMPLOYEE_CREATED,
        "Employee",
        employee.id,
        correlation_id,
        f"employee-created:{employee.id}",
        {"employee_id": str(employee.id)},
    )
    await session.commit()
    return employee


async def list_employees(session: AsyncSession, principal: Principal) -> list[Employee]:
    principal.require(EMPLOYEES_MANAGE)
    return await repository.list_employees(session, principal.tenant_id)


async def get_own_employee(session: AsyncSession, principal: Principal) -> Employee:
    principal.require("time.enter_own")
    employee = await repository.get_employee_by_user(
        session,
        principal.tenant_id,
        principal.user_id,
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee profile is not linked",
        )
    return employee


async def get_employee(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID,
) -> Employee:
    principal.require(EMPLOYEES_MANAGE)
    employee = await repository.get_employee(session, principal.tenant_id, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


async def approve_employee(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID,
    expected_version: int,
    data: EmployeeApproval,
) -> EmployeeApprovalRead:
    principal.require(EMPLOYEES_APPROVE)
    employee = await repository.get_employee(
        session,
        principal.tenant_id,
        employee_id,
        for_update=True,
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    existing = await repository.get_employee_provisioning_request(
        session,
        principal.tenant_id,
        employee.id,
    )
    if existing is not None and employee.status in {
        EmployeeStatus.IDENTITY_REQUESTED,
        EmployeeStatus.IDENTITY_CREATED,
    }:
        return EmployeeApprovalRead.model_validate(
            {
                "employee": employee,
                "provisioning": existing,
            }
        )
    if employee.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee version conflict",
        )
    if employee.status is not EmployeeStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee cannot be approved",
        )
    organization = await session.get(Organization, principal.tenant_id)
    domain = _identity_domain(organization)
    before = employee_audit_state(employee)
    employee.company_email = f"{employee.company_username}@{domain}"
    employee.google_org_unit_path = (
        employee.google_org_unit_path
        or (organization.google_default_org_unit_path if organization else None)
        or "/"
    )
    if not employee.google_org_unit_path.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google organizational unit path must begin with /",
        )
    employee.status = EmployeeStatus.IDENTITY_REQUESTED
    employee.approved_at = datetime.now(UTC)
    employee.approved_by = principal.user_id
    employee.updated_by = principal.user_id
    employee.version += 1
    provisioning = IdentityProvisioningRequest(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        employee_id=employee.id,
        idempotency_key=f"google-user:{employee.company_email}",
        primary_email=employee.company_email,
    )
    session.add(provisioning)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Employee",
        employee.id,
        "manager_approved",
        correlation_id,
        before,
        employee_audit_state(employee),
        data.reason,
    )
    add_outbox(
        session,
        principal,
        EMPLOYEE_PROVISIONING_REQUESTED,
        "IdentityProvisioningRequest",
        provisioning.id,
        correlation_id,
        f"employee-provisioning-requested:{provisioning.id}",
        {
            "employee_id": str(employee.id),
            "provisioning_request_id": str(provisioning.id),
        },
    )
    await session.commit()
    return EmployeeApprovalRead.model_validate(
        {
            "employee": employee,
            "provisioning": provisioning,
        }
    )


async def get_employee_provisioning(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID,
) -> IdentityProvisioningRequest:
    principal.require(EMPLOYEES_MANAGE)
    employee = await repository.get_employee(session, principal.tenant_id, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    request = await repository.get_employee_provisioning_request(
        session,
        principal.tenant_id,
        employee_id,
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provisioning request not found",
        )
    return request


async def reissue_employee_activation(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID,
    expected_version: int,
    data: EmployeeActivationReissue,
) -> EmployeeActivationRead:
    require_employee_activation(principal)
    employee = await repository.get_employee(
        session, principal.tenant_id, employee_id, for_update=True
    )
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if employee.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Employee version conflict"
        )
    activation = await issue_employee_activation(
        session,
        principal,
        employee,
        correlation_uuid(),
        data.reason,
    )
    await session.commit()
    return EmployeeActivationRead.model_validate(activation)


async def get_employee_activation_preview(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID,
) -> EmployeeActivationPreview:
    require_employee_activation(principal)
    if settings.email_provider != "mock":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    activation = await repository.get_active_activation_request(
        session, principal.tenant_id, employee_id
    )
    if activation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activation unavailable")
    token = _activation_token(activation, decrypt_secret(activation.encrypted_delivery_secret))
    return EmployeeActivationPreview(
        activation_url=f"{settings.frontend_url.rstrip('/')}/activate#token={token}",
        expires_at=activation.expires_at,
    )


async def issue_employee_activation(
    session: AsyncSession,
    principal: Principal,
    employee: Employee,
    correlation_id: uuid.UUID,
    reason: str,
) -> EmployeeActivationRequest:
    if employee.status is not EmployeeStatus.IDENTITY_CREATED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Google identity must exist before ERP activation",
        )
    existing = await repository.get_active_activation_request(
        session,
        principal.tenant_id,
        employee.id,
        for_update=True,
    )
    now = datetime.now(UTC)
    if existing is not None:
        existing.revoked_at = now
        existing.updated_by = principal.user_id
        existing.version += 1
        add_outbox(
            session,
            principal,
            EMPLOYEE_ACTIVATION_REVOKED,
            "EmployeeActivationRequest",
            existing.id,
            correlation_id,
            f"employee-activation-revoked:{existing.id}",
            {"employee_id": str(employee.id), "activation_request_id": str(existing.id)},
        )
    activation_id = uuid.uuid4()
    secret = secrets.token_urlsafe(48)
    token = f"{principal.tenant_id}.{activation_id}.{secret}"
    activation = EmployeeActivationRequest(
        id=activation_id,
        tenant_id=principal.tenant_id,
        employee_id=employee.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        encrypted_delivery_secret=encrypt_secret(secret),
        expires_at=now + timedelta(hours=settings.employee_activation_hours),
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    session.add(activation)
    await session.flush()
    add_audit(
        session,
        principal,
        "EmployeeActivationRequest",
        activation.id,
        "activation_requested",
        correlation_id,
        None,
        {
            "employee_id": str(employee.id),
            "expires_at": activation.expires_at.isoformat(),
            "version": activation.version,
        },
        reason,
    )
    add_outbox(
        session,
        principal,
        EMPLOYEE_ACTIVATION_REQUESTED,
        "EmployeeActivationRequest",
        activation.id,
        correlation_id,
        f"employee-activation-requested:{activation.id}",
        {"employee_id": str(employee.id), "activation_request_id": str(activation.id)},
    )
    return activation


def _activation_token(activation: EmployeeActivationRequest, secret: str) -> str:
    return f"{activation.tenant_id}.{activation.id}.{secret}"


def _identity_domain(organization: Organization | None) -> str:
    if organization is None or not organization.google_identity_domain:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company Google identity domain is not configured",
        )
    domain = organization.google_identity_domain.strip().lower().strip(".")
    if "." not in domain or not DOMAIN_PATTERN.fullmatch(domain):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company Google identity domain is invalid",
        )
    return domain
