import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from app.core.database import SessionFactory
from app.core.security import Principal, create_access_token
from app.core.tenancy import set_tenant_context
from app.main import app
from app.modules.people.models import Employee, EmployeeStatus
from app.modules.platform.models import (
    AuditEvent,
    InboxReceipt,
    LoginSession,
    Organization,
    OutboxEvent,
)
from app.modules.projects.models import Project
from app.modules.scheduling.models import Schedule, ScheduleActivity, ScheduleAssignment
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


async def test_manager_schedules_employee_and_conflicts_are_blocked() -> None:
    tenant_id = uuid.uuid4()
    manager = _principal(
        tenant_id,
        frozenset({"schedules.manage", "schedules.read"}),
    )
    employee_user_id = uuid.uuid4()
    employee_principal = _principal(
        tenant_id,
        frozenset({"schedules.read_own"}),
        user_id=employee_user_id,
    )
    project_id, employee_id = await _seed(
        manager,
        employee_principal,
        employee_user_id,
    )
    manager_headers = {"Authorization": f"Bearer {create_access_token(manager)}"}
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            headers=manager_headers,
        ) as client:
            schedule_response = await client.post(
                "/api/v1/schedules",
                json={
                    "project_id": str(project_id),
                    "name": "Construction Schedule",
                    "timezone": "America/Los_Angeles",
                },
            )
            assert schedule_response.status_code == 201, schedule_response.text
            schedule = schedule_response.json()
            activity = await _create_activity(client, schedule["id"], "1", 8, 12)
            assignment_response = await client.post(
                f"/api/v1/schedule-activities/{activity['id']}/assignments",
                headers={"If-Match": "1"},
                json={
                    "employee_id": str(employee_id),
                    "assignment_role": "Lead Carpenter",
                    "reason": "Crew plan approved by project manager",
                },
            )
            assert assignment_response.status_code == 201, assignment_response.text

            stale_response = await client.post(
                f"/api/v1/schedules/{schedule['id']}/activities",
                headers={"If-Match": "1"},
                json=_activity_payload("Stale", 13, 14),
            )
            assert stale_response.status_code == 409
            overlapping = await _create_activity(client, schedule["id"], "2", 11, 15)
            conflict_response = await client.post(
                f"/api/v1/schedule-activities/{overlapping['id']}/assignments",
                headers={"If-Match": "1"},
                json={
                    "employee_id": str(employee_id),
                    "reason": "Attempt conflicting assignment",
                },
            )
            assert conflict_response.status_code == 409
            assert "conflicting assignment" in conflict_response.json()["detail"]

            entries_response = await client.get(
                "/api/v1/schedule-entries",
                params={
                    "start_at": "2026-08-03T00:00:00-07:00",
                    "end_at": "2026-08-04T00:00:00-07:00",
                    "employee_id": str(employee_id),
                },
            )
            assert entries_response.status_code == 200
            entries = entries_response.json()
            assert len(entries) == 1
            assert entries[0]["employee_name"] == "Ada Builder"
            assert entries[0]["project_name"] == "Test Construction Project"

        own_headers = {
            "Authorization": f"Bearer {create_access_token(employee_principal)}"
        }
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            headers=own_headers,
        ) as client:
            own_response = await client.get(
                "/api/v1/schedule-entries",
                params={
                    "start_at": "2026-08-03T00:00:00-07:00",
                    "end_at": "2026-08-04T00:00:00-07:00",
                    "employee_id": str(uuid.uuid4()),
                },
            )
        assert own_response.status_code == 200
        assert len(own_response.json()) == 1
        await _assert_audit_and_isolation(tenant_id)
    finally:
        await _clean_tenant(tenant_id)


async def test_schedule_permissions_and_timezone_validation() -> None:
    tenant_id = uuid.uuid4()
    denied = _principal(tenant_id, frozenset({"schedules.read"}))
    project_id, _ = await _seed(denied)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://benson-ai",
            headers={"Authorization": f"Bearer {create_access_token(denied)}"},
        ) as client:
            denied_response = await client.post(
                "/api/v1/schedules",
                json={
                    "project_id": str(project_id),
                    "name": "Denied",
                },
            )
            naive_response = await client.get(
                "/api/v1/schedule-entries",
                params={
                    "start_at": "2026-08-03T00:00:00",
                    "end_at": "2026-08-04T00:00:00",
                },
            )
        assert denied_response.status_code == 403
        assert naive_response.status_code == 422
    finally:
        await _clean_tenant(tenant_id)


async def _create_activity(
    client: AsyncClient,
    schedule_id: str,
    version: str,
    start_hour: int,
    end_hour: int,
) -> dict:
    response = await client.post(
        f"/api/v1/schedules/{schedule_id}/activities",
        headers={"If-Match": version},
        json=_activity_payload("Foundation work", start_hour, end_hour),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _activity_payload(title: str, start_hour: int, end_hour: int) -> dict[str, str]:
    return {
        "title": title,
        "description": "Form and place concrete",
        "start_at": f"2026-08-03T{start_hour:02}:00:00-07:00",
        "end_at": f"2026-08-03T{end_hour:02}:00:00-07:00",
        "location": "100 Test Site Road",
        "required_tools": "PPE, hand tools",
    }


def _principal(
    tenant_id: uuid.UUID,
    permissions: frozenset[str],
    *,
    user_id: uuid.UUID | None = None,
) -> Principal:
    return Principal(
        user_id=user_id or uuid.uuid4(),
        tenant_id=tenant_id,
        session_id=uuid.uuid4(),
        permissions=permissions,
    )


async def _seed(
    principal: Principal,
    employee_principal: Principal | None = None,
    employee_user_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    project_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=principal.tenant_id,
                name="Schedule Test",
                slug=f"schedule-test-{principal.tenant_id}",
            )
        )
        await set_tenant_context(session, principal.tenant_id)
        sessions = [
            LoginSession(
                id=principal.session_id,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                refresh_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        ]
        if employee_principal is not None:
            sessions.append(
                LoginSession(
                    id=employee_principal.session_id,
                    tenant_id=principal.tenant_id,
                    user_id=employee_principal.user_id,
                    refresh_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        session.add_all(sessions)
        session.add(
            Project(
                id=project_id,
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                updated_by=principal.user_id,
                proposal_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                property_id=uuid.uuid4(),
                project_number="P-SCHEDULE",
                name="Test Construction Project",
            )
        )
        session.add(
            Employee(
                id=employee_id,
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                updated_by=principal.user_id,
                employee_number="E-SCHEDULE",
                first_name="Ada",
                last_name="Builder",
                personal_email="ada@example.com",
                company_username="ada.builder",
                company_email="ada.builder@bensonhomesolutions.com",
                hire_date=date(2026, 8, 3),
                status=EmployeeStatus.IDENTITY_CREATED,
                user_id=employee_user_id,
            )
        )
    return project_id, employee_id


async def _assert_audit_and_isolation(tenant_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        actions = set(
            await session.scalars(
                select(AuditEvent.action).where(AuditEvent.tenant_id == tenant_id)
            )
        )
        assert {"created", "employee_assigned"} <= actions
    async with SessionFactory() as other_tenant:
        await set_tenant_context(other_tenant, uuid.uuid4())
        assert await other_tenant.scalar(select(Schedule)) is None
        assert await other_tenant.scalar(select(ScheduleActivity)) is None
        assert await other_tenant.scalar(select(ScheduleAssignment)) is None


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        for model in (
            InboxReceipt,
            ScheduleAssignment,
            ScheduleActivity,
            Schedule,
            Employee,
            Project,
            OutboxEvent,
            AuditEvent,
            LoginSession,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Organization).where(Organization.id == tenant_id))
