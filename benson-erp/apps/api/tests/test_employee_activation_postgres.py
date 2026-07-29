import json
import os
import uuid
from datetime import date

import pytest
from app.core.database import SessionFactory
from app.core.encryption import decrypt_secret
from app.core.security import Principal
from app.core.tenancy import set_tenant_context
from app.integrations.email import MockEmailProvider
from app.main import app
from app.modules.people import handlers as people_handlers
from app.modules.people import service as people_service
from app.modules.people.events import (
    EMPLOYEE_ACTIVATION_REQUESTED,
    EMPLOYEE_ACTIVATION_SENT,
    GOOGLE_IDENTITY_CREATED,
)
from app.modules.people.models import Employee, EmployeeActivationRequest, EmployeeStatus
from app.modules.people.service import issue_employee_activation
from app.modules.platform.auth_service import EMPLOYEE_SELF_SERVICE_PERMISSIONS
from app.modules.platform.models import (
    AuditEvent,
    InboxReceipt,
    LoginEvent,
    LoginSession,
    Membership,
    Organization,
    OutboxEvent,
    User,
)
from app.workers.processor import ProcessingOutcome, process_event
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


async def test_employee_activation_links_least_privilege_user_and_is_single_use() -> None:
    tenant_id = uuid.uuid4()
    manager_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    principal = Principal(
        tenant_id=tenant_id,
        user_id=manager_id,
        session_id=uuid.uuid4(),
        permissions=frozenset({"employees.activate"}),
    )
    await _seed_identity_ready_employee(tenant_id, manager_id, employee_id)
    try:
        async with SessionFactory() as session:
            await set_tenant_context(session, tenant_id)
            employee = await session.get(Employee, employee_id)
            assert employee is not None
            activation = await issue_employee_activation(
                session,
                principal,
                employee,
                uuid.uuid4(),
                "Integration test activation request",
            )
            secret = decrypt_secret(activation.encrypted_delivery_secret)
            token = f"{tenant_id}.{activation.id}.{secret}"
            await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://benson-ai"
        ) as client:
            inspected = await client.post(
                "/api/v1/auth/employee-activations/inspect", json={"token": token}
            )
            assert inspected.status_code == 200, inspected.text
            assert inspected.json()["company_email"] == "field.worker@bensonhomesolutions.com"

            completed = await client.post(
                "/api/v1/auth/employee-activations/complete",
                json={"token": token, "password": "Field-Activation-Passphrase-2026"},
            )
            assert completed.status_code == 200, completed.text
            assert completed.json() == {
                "activated": True,
                "organization": f"activation-{tenant_id}",
                "email": "field.worker@bensonhomesolutions.com",
            }
            replay = await client.post(
                "/api/v1/auth/employee-activations/complete",
                json={"token": token, "password": "Field-Activation-Passphrase-2026"},
            )
            assert replay.status_code == 400
            login = await client.post(
                "/api/v1/auth/login",
                json={
                    "organization": f"activation-{tenant_id}",
                    "email": "field.worker@bensonhomesolutions.com",
                    "password": "Field-Activation-Passphrase-2026",
                },
            )
            assert login.status_code == 200, login.text

        async with SessionFactory() as session:
            await set_tenant_context(session, tenant_id)
            employee = await session.get(Employee, employee_id)
            assert employee is not None
            assert employee.status is EmployeeStatus.ACTIVE
            assert employee.user_id is not None
            membership = await session.scalar(
                select(Membership).where(
                    Membership.tenant_id == tenant_id,
                    Membership.user_id == employee.user_id,
                )
            )
            assert membership is not None
            assert membership.permissions == EMPLOYEE_SELF_SERVICE_PERMISSIONS
            activation = await session.scalar(
                select(EmployeeActivationRequest).where(
                    EmployeeActivationRequest.tenant_id == tenant_id
                )
            )
            assert activation is not None
            assert activation.used_at is not None
            assert activation.encrypted_delivery_secret == ""
            outbox_payloads = list(
                await session.scalars(
                    select(OutboxEvent.payload).where(OutboxEvent.tenant_id == tenant_id)
                )
            )
            audit_states = list(
                (
                    event.before_state,
                    event.after_state,
                    event.reason,
                )
                for event in await session.scalars(
                    select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
                )
            )
            assert secret not in json.dumps(outbox_payloads)
            assert secret not in json.dumps(audit_states)
    finally:
        await _cleanup(tenant_id, manager_id)


async def test_activation_handlers_are_idempotent_and_keep_secret_out_of_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    manager_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    provider = MockEmailProvider()
    monkeypatch.setattr(people_handlers.settings, "email_provider", "mock")
    monkeypatch.setattr(people_service.settings, "email_provider", "mock")
    monkeypatch.setattr(
        people_handlers,
        "build_email_provider",
        lambda _settings: provider,
    )
    await _seed_identity_ready_employee(tenant_id, manager_id, employee_id)
    try:
        async with SessionFactory() as session:
            await set_tenant_context(session, tenant_id)
            google_event = OutboxEvent(
                tenant_id=tenant_id,
                event_type=GOOGLE_IDENTITY_CREATED,
                aggregate_type="Employee",
                aggregate_id=employee_id,
                payload={"employee_id": str(employee_id)},
                correlation_id=correlation_id,
                idempotency_key=f"test-google-identity-created:{employee_id}",
            )
            session.add(google_event)
            await session.commit()
            google_event_id = google_event.id

        first_issue = await process_event(tenant_id, google_event_id)
        second_issue = await process_event(tenant_id, google_event_id)
        assert first_issue.outcome is ProcessingOutcome.PUBLISHED
        assert second_issue.outcome is ProcessingOutcome.ALREADY_PUBLISHED

        async with SessionFactory() as session:
            await set_tenant_context(session, tenant_id)
            activation = await session.get(
                EmployeeActivationRequest,
                await session.scalar(
                    select(OutboxEvent.aggregate_id).where(
                        OutboxEvent.tenant_id == tenant_id,
                        OutboxEvent.event_type == EMPLOYEE_ACTIVATION_REQUESTED,
                    )
                ),
            )
            assert activation is not None
            secret = decrypt_secret(activation.encrypted_delivery_secret)
            activation_events = list(
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.tenant_id == tenant_id,
                        OutboxEvent.event_type == EMPLOYEE_ACTIVATION_REQUESTED,
                    )
                )
            )
            assert len(activation_events) == 1
            activation_event = activation_events[0]
            activation_id = activation.id
            assert secret not in json.dumps(activation_event.payload)
            activation_event_id = activation_event.id

        first_delivery = await process_event(tenant_id, activation_event_id)
        second_delivery = await process_event(tenant_id, activation_event_id)
        assert first_delivery.outcome is ProcessingOutcome.PUBLISHED
        assert second_delivery.outcome is ProcessingOutcome.ALREADY_PUBLISHED
        assert len(provider.sent) == 1
        message = provider.sent[0]
        assert message.personal_email == "field.worker@example.com"
        assert message.company_username == "field.worker@bensonhomesolutions.com"
        assert message.activation_url.endswith(
            f"/activate#token={tenant_id}.{activation.id}.{secret}"
        )
        assert message.gmail_unlicensed_statement

        async with SessionFactory() as session:
            await set_tenant_context(session, tenant_id)
            activation = await session.get(EmployeeActivationRequest, activation_id)
            assert activation is not None
            principal = Principal(
                tenant_id=tenant_id,
                user_id=manager_id,
                session_id=uuid.uuid4(),
                permissions=frozenset({"employees.manage"}),
            )
            preview = await people_service.get_employee_activation_preview(
                session, principal, employee_id
            )
            assert preview.activation_url == message.activation_url

            employee = await session.get(Employee, employee_id)
            assert employee is not None
            assert activation.sent_at is not None
            assert activation.attempt_count == 1
            assert employee.activation_sent_at == activation.sent_at
            sent_events = list(
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.tenant_id == tenant_id,
                        OutboxEvent.event_type == EMPLOYEE_ACTIVATION_SENT,
                    )
                )
            )
            assert len(sent_events) == 1

            outbox_payloads = list(
                await session.scalars(
                    select(OutboxEvent.payload).where(OutboxEvent.tenant_id == tenant_id)
                )
            )
            audit_events = list(
                await session.scalars(
                    select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
                )
            )
            audit_payloads = [
                {
                    "before_state": event.before_state,
                    "after_state": event.after_state,
                    "reason": event.reason,
                }
                for event in audit_events
            ]
            assert secret not in json.dumps(outbox_payloads)
            assert secret not in json.dumps(audit_payloads)
    finally:
        await _cleanup(tenant_id, manager_id)


async def _seed_identity_ready_employee(
    tenant_id: uuid.UUID,
    manager_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=tenant_id,
                name="Activation Test",
                slug=f"activation-{tenant_id}",
                google_identity_domain="bensonhomesolutions.com",
            )
        )
        await set_tenant_context(session, tenant_id)
        session.add(
            Employee(
                id=employee_id,
                tenant_id=tenant_id,
                employee_number="E-ACTIVATE",
                first_name="Field",
                last_name="Worker",
                personal_email="field.worker@example.com",
                company_username="field.worker",
                company_email="field.worker@bensonhomesolutions.com",
                hire_date=date.today(),
                google_subject_id=str(uuid.uuid4()),
                status=EmployeeStatus.IDENTITY_CREATED,
                created_by=manager_id,
                updated_by=manager_id,
            )
        )


async def _cleanup(tenant_id: uuid.UUID, manager_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        user_ids = list(
            await session.scalars(
                select(Membership.user_id).where(Membership.tenant_id == tenant_id)
            )
        )
        for model in (
            InboxReceipt,
            LoginEvent,
            LoginSession,
            Membership,
            EmployeeActivationRequest,
            Employee,
            OutboxEvent,
            AuditEvent,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.execute(delete(User).where(User.id == manager_id))
        await session.execute(delete(Organization).where(Organization.id == tenant_id))
