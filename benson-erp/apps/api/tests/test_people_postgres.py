import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from app.core.database import SessionFactory
from app.core.security import Principal, create_access_token
from app.core.tenancy import set_tenant_context
from app.integrations.google_directory import MockDirectoryProvider
from app.main import app
from app.modules.people.handlers import provision_google_identity
from app.modules.people.models import (
    Employee,
    IdentityProvisioningRequest,
)
from app.modules.platform.models import (
    AuditEvent,
    InboxReceipt,
    LoginSession,
    Organization,
    OutboxEvent,
)
from app.workers.processor import ProcessingOutcome, process_event
from app.workers.registry import HandlerRegistry
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="PostgreSQL integration tests disabled",
    ),
]


async def test_employee_approval_requests_and_provisions_google_identity() -> None:
    tenant_id = uuid.uuid4()
    principal = _principal(tenant_id)
    await _seed_session(principal)
    headers = {"Authorization": f"Bearer {create_access_token(principal)}"}
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            headers=headers,
        ) as client:
            created_response = await client.post(
                "/api/v1/employees",
                json={
                    "employee_number": "E-100",
                    "first_name": "Ada",
                    "last_name": "Builder",
                    "preferred_name": "Ada",
                    "personal_email": "ada@example.com",
                    "company_username": "ada.builder",
                    "hire_date": "2026-08-03",
                    "google_org_unit_path": "/Employees/Field",
                },
            )
            assert created_response.status_code == 201, created_response.text
            employee = created_response.json()
            assert employee["status"] == "DRAFT"
            approved_response = await client.post(
                f"/api/v1/employees/{employee['id']}/approve",
                headers={"If-Match": "1"},
                json={"reason": "Offer accepted and hiring file approved"},
            )
            assert approved_response.status_code == 200, approved_response.text
            approved = approved_response.json()
            assert approved["employee"]["status"] == "IDENTITY_REQUESTED"
            assert (
                approved["employee"]["company_email"]
                == "ada.builder@bensonhomesolutions.com"
            )
            assert approved["provisioning"]["status"] == "PENDING"
            repeated = await client.post(
                f"/api/v1/employees/{employee['id']}/approve",
                headers={"If-Match": "1"},
                json={"reason": "Safe command retry"},
            )
            assert repeated.status_code == 200
            assert repeated.json()["provisioning"]["id"] == approved["provisioning"]["id"]

        event = await _provisioning_event(tenant_id)
        registry = HandlerRegistry()

        async def handler(session, outbox_event):
            return await provision_google_identity(
                session,
                outbox_event,
                MockDirectoryProvider(),
            )

        registry.register("EmployeeProvisioningRequested", "test-google-directory", handler)
        result = await process_event(tenant_id, event.id, registry)
        assert result.outcome is ProcessingOutcome.PUBLISHED

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            headers=headers,
        ) as client:
            provisioning_response = await client.get(
                f"/api/v1/employees/{employee['id']}/provisioning"
            )
            employee_response = await client.get(f"/api/v1/employees/{employee['id']}")
        assert provisioning_response.status_code == 200
        assert provisioning_response.json()["status"] == "CREATED"
        assert provisioning_response.json()["external_user_id"]
        assert employee_response.json()["status"] == "IDENTITY_CREATED"
        assert employee_response.json()["google_subject_id"]
        await _assert_audit_and_tenant_isolation(tenant_id, uuid.UUID(employee["id"]))
    finally:
        await _clean_tenant(tenant_id)


async def test_employee_permissions_are_enforced() -> None:
    tenant_id = uuid.uuid4()
    principal = _principal(tenant_id, permissions=frozenset())
    await _seed_session(principal)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            headers={"Authorization": f"Bearer {create_access_token(principal)}"},
        ) as client:
            response = await client.post(
                "/api/v1/employees",
                json={
                    "employee_number": "E-DENIED",
                    "first_name": "No",
                    "last_name": "Access",
                    "personal_email": "denied@example.com",
                    "company_username": "no.access",
                    "hire_date": str(date.today()),
                },
            )
        assert response.status_code == 403
    finally:
        await _clean_tenant(tenant_id)


def _principal(
    tenant_id: uuid.UUID,
    *,
    permissions: frozenset[str] = frozenset(
        {"employees.manage", "employees.approve"}
    ),
) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        session_id=uuid.uuid4(),
        permissions=permissions,
    )


async def _seed_session(principal: Principal) -> None:
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=principal.tenant_id,
                name="Benson People Test",
                slug=f"benson-people-{principal.tenant_id}",
                google_identity_domain="bensonhomesolutions.com",
                google_customer_id="C0123",
                google_default_org_unit_path="/Employees",
            )
        )
        await set_tenant_context(session, principal.tenant_id)
        session.add(
            LoginSession(
                id=principal.session_id,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                refresh_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )


async def _provisioning_event(tenant_id: uuid.UUID) -> OutboxEvent:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "EmployeeProvisioningRequested",
            )
        )
        assert event is not None
        return event


async def _assert_audit_and_tenant_isolation(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        audit = list(
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.record_type == "Employee",
                    AuditEvent.record_id == employee_id,
                )
            )
        )
        assert {event.action for event in audit} == {
            "created",
            "manager_approved",
            "google_identity_created",
        }
        assert "personal_email" not in str(
            [(event.before_state, event.after_state) for event in audit]
        )
    async with SessionFactory() as other_tenant:
        await set_tenant_context(other_tenant, uuid.uuid4())
        leaked = await other_tenant.get(Employee, employee_id)
        assert leaked is None


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        for model in (
            InboxReceipt,
            IdentityProvisioningRequest,
            Employee,
            OutboxEvent,
            AuditEvent,
            LoginSession,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Organization).where(Organization.id == tenant_id))
