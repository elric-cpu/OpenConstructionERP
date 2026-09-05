import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import decrypt_secret
from app.core.security import Principal
from app.integrations.email import ActivationEmailInput, build_email_provider
from app.integrations.google_directory import (
    DirectoryIdentityInput,
    DirectoryProvider,
    build_directory_provider,
)
from app.modules.people import repository, service
from app.modules.people.events import EMPLOYEE_ACTIVATION_SENT, GOOGLE_IDENTITY_CREATED
from app.modules.people.models import EmployeeStatus, IdentityProvisioningStatus
from app.modules.platform.models import AuditEvent, Organization, OutboxEvent


async def provision_google_identity(
    session: AsyncSession,
    event: OutboxEvent,
    provider: DirectoryProvider,
) -> dict[str, str]:
    request_id = uuid.UUID(event.payload["provisioning_request_id"])
    request = await repository.get_provisioning_request(
        session,
        event.tenant_id,
        request_id,
    )
    if request is None:
        raise RuntimeError("Provisioning request is unavailable")
    employee = await repository.get_employee(
        session,
        event.tenant_id,
        request.employee_id,
        for_update=True,
    )
    if employee is None:
        raise RuntimeError("Provisioning employee is unavailable")
    if request.status is IdentityProvisioningStatus.CREATED:
        return {
            "employee_id": str(employee.id),
            "external_user_id": request.external_user_id or "",
        }
    identity = await provider.create_identity(
        DirectoryIdentityInput(
            primary_email=request.primary_email,
            first_name=employee.first_name,
            last_name=employee.last_name,
            recovery_email=employee.personal_email,
            org_unit_path=employee.google_org_unit_path or "/",
            temporary_password=secrets.token_urlsafe(32),
        )
    )
    now = datetime.now(UTC)
    request.status = IdentityProvisioningStatus.CREATED
    request.external_user_id = identity.subject_id
    request.completed_at = now
    request.updated_by = request.created_by
    request.version += 1
    employee.status = EmployeeStatus.IDENTITY_CREATED
    employee.company_email = identity.primary_email
    employee.google_subject_id = identity.subject_id
    employee.identity_created_at = now
    employee.updated_by = request.created_by
    employee.version += 1
    session.add(
        AuditEvent(
            tenant_id=event.tenant_id,
            actor_id=request.created_by,
            record_type="Employee",
            record_id=employee.id,
            action="google_identity_created",
            before_state={"status": EmployeeStatus.IDENTITY_REQUESTED},
            after_state={
                "status": employee.status,
                "company_email": employee.company_email,
                "version": employee.version,
            },
            correlation_id=event.correlation_id,
            reason="Completed by durable Google Directory provisioning handler",
        )
    )
    session.add(
        OutboxEvent(
            tenant_id=event.tenant_id,
            event_type=GOOGLE_IDENTITY_CREATED,
            aggregate_type="Employee",
            aggregate_id=employee.id,
            payload={
                "employee_id": str(employee.id),
                "provisioning_request_id": str(request.id),
            },
            correlation_id=event.correlation_id,
            idempotency_key=f"google-identity-created:{request.id}",
        )
    )
    return {
        "employee_id": str(employee.id),
        "external_user_id": identity.subject_id,
    }


async def handle_employee_provisioning_requested(
    session: AsyncSession,
    event: OutboxEvent,
) -> dict[str, str]:
    return await provision_google_identity(
        session,
        event,
        build_directory_provider(settings),
    )


async def handle_google_identity_created(
    session: AsyncSession,
    event: OutboxEvent,
) -> dict[str, str]:
    employee = await repository.get_employee(
        session,
        event.tenant_id,
        uuid.UUID(event.payload["employee_id"]),
        for_update=True,
    )
    if employee is None:
        raise RuntimeError("Activation employee is unavailable")
    existing = await repository.get_active_activation_request(
        session, event.tenant_id, employee.id
    )
    if existing is not None:
        return {"activation_request_id": str(existing.id), "employee_id": str(employee.id)}
    principal = Principal(
        user_id=employee.approved_by or employee.updated_by,
        tenant_id=event.tenant_id,
        permissions=frozenset({"employees.activate"}),
        session_id=uuid.uuid4(),
    )
    activation = await service.issue_employee_activation(
        session,
        principal,
        employee,
        event.correlation_id,
        "Google identity created; ERP activation requested",
    )
    return {"activation_request_id": str(activation.id), "employee_id": str(employee.id)}


async def handle_employee_activation_requested(
    session: AsyncSession,
    event: OutboxEvent,
) -> dict[str, str]:
    activation = await repository.get_activation_request(
        session,
        event.tenant_id,
        uuid.UUID(event.payload["activation_request_id"]),
        for_update=True,
    )
    if activation is None:
        raise RuntimeError("Activation request is unavailable")
    if activation.sent_at is not None:
        return {"activation_request_id": str(activation.id), "status": "sent"}
    employee = await repository.get_employee(
        session, event.tenant_id, activation.employee_id, for_update=True
    )
    organization = await session.get(Organization, event.tenant_id)
    if employee is None or organization is None:
        raise RuntimeError("Activation delivery context is unavailable")
    secret = decrypt_secret(activation.encrypted_delivery_secret)
    token = f"{event.tenant_id}.{activation.id}.{secret}"
    frontend = settings.frontend_url.rstrip("/")
    await build_email_provider(settings).send_activation_email(
        ActivationEmailInput(
            personal_email=employee.personal_email,
            company_username=employee.company_email or employee.company_username,
            google_sign_in_url="https://accounts.google.com/",
            erp_sign_in_url=f"{frontend}/login",
            activation_url=f"{frontend}/activate#token={token}",
            expires_at=activation.expires_at,
            support_details=settings.employee_support_details,
            gmail_unlicensed_statement=(
                "Gmail may be unavailable while your company-managed identity is unlicensed."
            ),
        )
    )
    now = datetime.now(UTC)
    activation.sent_at = now
    activation.last_attempt_at = now
    activation.attempt_count += 1
    activation.updated_by = activation.created_by
    activation.version += 1
    if settings.email_provider != "mock":
        activation.encrypted_delivery_secret = ""
    employee.activation_sent_at = now
    employee.updated_by = activation.created_by
    employee.version += 1
    session.add(
        AuditEvent(
            tenant_id=event.tenant_id,
            actor_id=activation.created_by,
            record_type="EmployeeActivationRequest",
            record_id=activation.id,
            action="activation_email_sent",
            before_state={"sent_at": None},
            after_state={"sent_at": now.isoformat(), "version": activation.version},
            correlation_id=event.correlation_id,
            reason="Delivered to the approved personal email address",
        )
    )
    session.add(
        OutboxEvent(
            tenant_id=event.tenant_id,
            event_type=EMPLOYEE_ACTIVATION_SENT,
            aggregate_type="EmployeeActivationRequest",
            aggregate_id=activation.id,
            payload={"activation_request_id": str(activation.id), "employee_id": str(employee.id)},
            correlation_id=event.correlation_id,
            idempotency_key=f"employee-activation-sent:{activation.id}",
        )
    )
    return {"activation_request_id": str(activation.id), "status": "sent"}
