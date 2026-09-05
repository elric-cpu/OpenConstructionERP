import os
import uuid
from datetime import UTC, date, datetime, time, timedelta

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
from app.modules.timekeeping.models import (
    TimeCorrection,
    TimeCorrectionStatus,
    TimeEntry,
    TimeEntryStatus,
)
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


async def test_time_entry_employee_options_are_self_only_without_team_permission() -> None:
    tenant_id = uuid.uuid4()
    employee_principal = _principal(
        tenant_id,
        frozenset({"projects.read", "time.enter_own", "time.certify_own"}),
    )
    supervisor = _principal(
        tenant_id,
        frozenset({"time.enter_team", "time.approve_team", "time.read_team"}),
    )
    _, employee_id, _ = await _seed(employee_principal, supervisor)
    teammate_id = uuid.uuid4()
    try:
        async with SessionFactory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            session.add(
                Employee(
                    id=teammate_id,
                    tenant_id=tenant_id,
                    created_by=supervisor.user_id,
                    updated_by=supervisor.user_id,
                    employee_number="E-TEAM",
                    first_name="Grace",
                    last_name="Carpenter",
                    personal_email="grace-time@example.com",
                    company_username="grace.time",
                    hire_date=date.today() - timedelta(days=20),
                    status=EmployeeStatus.ACTIVE,
                )
            )

        async with _client(employee_principal) as client:
            options_response = await client.get(
                "/api/v1/time-entries/resources/employees"
            )
            assert options_response.status_code == 200, options_response.text
            assert options_response.json() == [
                {
                    "id": str(employee_id),
                    "employee_number": "E-TIME",
                    "first_name": "Ada",
                    "last_name": "Builder",
                    "is_self": True,
                }
            ]
            own_response = await client.get("/api/v1/employees/me")
            assert own_response.status_code == 200
            assert own_response.json()["id"] == str(employee_id)
            employee_directory = await client.get("/api/v1/employees")
            assert employee_directory.status_code == 403

        async with _client(supervisor) as client:
            options_response = await client.get(
                "/api/v1/time-entries/resources/employees"
            )
            assert options_response.status_code == 200
            assert {item["id"] for item in options_response.json()} == {
                str(employee_id),
                str(teammate_id),
            }
            assert all(not item["is_self"] for item in options_response.json())
    finally:
        await _clean_tenant(tenant_id)


async def test_employee_certifies_and_supervisor_approves_immutable_time() -> None:
    tenant_id = uuid.uuid4()
    employee_principal = _principal(
        tenant_id,
        frozenset({"time.enter_own", "time.certify_own"}),
    )
    supervisor = _principal(
        tenant_id,
        frozenset({"time.enter_team", "time.approve_team", "time.read_team"}),
    )
    project_id, employee_id, assignment_id = await _seed(
        employee_principal,
        supervisor,
    )
    operation_id = uuid.uuid4()
    payload = _payload(operation_id, project_id, assignment_id)
    try:
        async with _client(employee_principal) as client:
            created_response = await client.post("/api/v1/time-entries", json=payload)
            assert created_response.status_code == 201, created_response.text
            created = created_response.json()
            assert created["status"] == "DRAFT"
            assert created["total_hours"] == "8.00"
            repeated_response = await client.post("/api/v1/time-entries", json=payload)
            assert repeated_response.status_code == 201
            assert repeated_response.json()["id"] == created["id"]
            certified_response = await client.post(
                f"/api/v1/time-entries/{created['id']}/certify",
                headers={"If-Match": "1"},
                json={
                    "statement": (
                        "I certify this record accurately reflects all hours I worked."
                    )
                },
            )
            assert certified_response.status_code == 200, certified_response.text
            certified = certified_response.json()
            assert certified["status"] == "CERTIFIED"

        async with _client(supervisor) as client:
            approved_response = await client.post(
                f"/api/v1/time-entries/{created['id']}/approve",
                headers={"If-Match": "2"},
                json={"reason": "Work and charge allocation verified against daily plan"},
            )
            assert approved_response.status_code == 200, approved_response.text
            approved = approved_response.json()
            assert approved["status"] == "APPROVED"
            entries_response = await client.get(
                "/api/v1/time-entries",
                params={
                    "date_from": str(date.today() - timedelta(days=1)),
                    "date_to": str(date.today()),
                    "employee_id": str(employee_id),
                },
            )
            assert entries_response.status_code == 200
            assert len(entries_response.json()) == 1

        async with _client(employee_principal) as client:
            recertify_response = await client.post(
                f"/api/v1/time-entries/{created['id']}/certify",
                headers={"If-Match": "3"},
                json={"statement": "Attempt to replace a previously certified record."},
            )
        assert recertify_response.status_code == 409
        await _assert_history_and_isolation(tenant_id, uuid.UUID(created["id"]))
    finally:
        await _clean_tenant(tenant_id)


async def test_timekeeping_rejects_overlap_bad_totals_and_supervisor_certification() -> None:
    tenant_id = uuid.uuid4()
    employee_principal = _principal(
        tenant_id,
        frozenset({"time.enter_own", "time.certify_own"}),
    )
    supervisor = _principal(
        tenant_id,
        frozenset({"time.enter_team", "time.approve_team"}),
    )
    project_id, employee_id, assignment_id = await _seed(
        employee_principal,
        supervisor,
    )
    try:
        async with _client(supervisor) as client:
            crew_payload = _payload(uuid.uuid4(), project_id, assignment_id)
            crew_payload["employee_id"] = str(employee_id)
            crew_payload["source"] = "CREW"
            created_response = await client.post("/api/v1/time-entries", json=crew_payload)
            assert created_response.status_code == 201
            created = created_response.json()
            certification_response = await client.post(
                f"/api/v1/time-entries/{created['id']}/certify",
                headers={"If-Match": "1"},
                json={"statement": "Supervisor must not impersonate the employee."},
            )
            assert certification_response.status_code == 403

        async with _client(employee_principal) as client:
            overlap_payload = _payload(uuid.uuid4(), project_id, assignment_id)
            overlap_response = await client.post(
                "/api/v1/time-entries",
                json=overlap_payload,
            )
            assert overlap_response.status_code == 409
            bad_total = _payload(uuid.uuid4(), project_id, assignment_id)
            bad_total["start_at"] = _timestamp(17)
            bad_total["end_at"] = _timestamp(19)
            bad_total["regular_hours"] = "1.00"
            bad_total_response = await client.post(
                "/api/v1/time-entries",
                json=bad_total,
            )
            assert bad_total_response.status_code == 422
            assert "Classified hours" in bad_total_response.json()["detail"]
    finally:
        await _clean_tenant(tenant_id)


async def test_time_correction_preserves_original_and_requires_reapproval() -> None:
    tenant_id = uuid.uuid4()
    employee_principal = _principal(
        tenant_id,
        frozenset({"time.enter_own", "time.certify_own", "time.correct_own"}),
    )
    supervisor = _principal(
        tenant_id,
        frozenset(
            {
                "time.enter_team",
                "time.approve_team",
                "time.read_team",
                "time.correct_team",
            }
        ),
    )
    project_id, _, assignment_id = await _seed(employee_principal, supervisor)
    try:
        async with _client(employee_principal) as client:
            created = (
                await client.post(
                    "/api/v1/time-entries",
                    json=_payload(uuid.uuid4(), project_id, assignment_id),
                )
            ).json()
            certified = await client.post(
                f"/api/v1/time-entries/{created['id']}/certify",
                headers={"If-Match": "1"},
                json={"statement": "I certify the original hours before correction."},
            )
            assert certified.status_code == 200
        async with _client(supervisor) as client:
            approved = await client.post(
                f"/api/v1/time-entries/{created['id']}/approve",
                headers={"If-Match": "2"},
                json={"reason": "Original time reviewed before correction request"},
            )
            assert approved.status_code == 200

        replacement_payload = _payload(uuid.uuid4(), project_id, assignment_id)
        replacement_payload["end_at"] = _timestamp(17)
        replacement_payload["regular_hours"] = "8.00"
        replacement_payload["overtime_hours"] = "1.00"
        replacement_payload["description"] = "Corrected record adds one hour of cleanup"
        async with _client(employee_principal) as client:
            correction_response = await client.post(
                f"/api/v1/time-entries/{created['id']}/corrections",
                headers={"If-Match": "3"},
                json={
                    "reason": "Employee discovered one omitted cleanup hour.",
                    "replacement": replacement_payload,
                },
            )
            assert correction_response.status_code == 201, correction_response.text
            correction = correction_response.json()
            assert correction["status"] == "PENDING_RECERTIFICATION"
            assert correction["replacement"]["status"] == "DRAFT"
            assert correction["replacement"]["total_hours"] == "9.00"
            replacement_id = correction["replacement_entry_id"]
            repeated = await client.post(
                f"/api/v1/time-entries/{created['id']}/corrections",
                headers={"If-Match": "3"},
                json={
                    "reason": "Employee discovered one omitted cleanup hour.",
                    "replacement": replacement_payload,
                },
            )
            assert repeated.status_code == 201
            assert repeated.json()["id"] == correction["id"]
            assert repeated.json()["replacement_entry_id"] == replacement_id
            recertified = await client.post(
                f"/api/v1/time-entries/{replacement_id}/certify",
                headers={"If-Match": "1"},
                json={"statement": "I certify the corrected nine-hour record is accurate."},
            )
            assert recertified.status_code == 200, recertified.text

        async with _client(supervisor) as client:
            reapproved = await client.post(
                f"/api/v1/time-entries/{replacement_id}/approve",
                headers={"If-Match": "2"},
                json={"reason": "Correction and added cleanup hour verified"},
            )
            assert reapproved.status_code == 200, reapproved.text
        async with SessionFactory() as session:
            await set_tenant_context(session, tenant_id)
            original = await session.get(TimeEntry, uuid.UUID(created["id"]))
            replacement = await session.get(TimeEntry, uuid.UUID(replacement_id))
            persisted = await session.get(TimeCorrection, uuid.UUID(correction["id"]))
            assert original is not None
            assert original.status is TimeEntryStatus.CORRECTED
            assert original.total_hours == 8
            assert replacement is not None
            assert replacement.status is TimeEntryStatus.APPROVED
            assert replacement.total_hours == 9
            assert persisted is not None
            assert persisted.status is TimeCorrectionStatus.COMPLETED
            assert persisted.completed_at is not None
    finally:
        await _clean_tenant(tenant_id)


def _payload(
    operation_id: uuid.UUID,
    project_id: uuid.UUID,
    assignment_id: uuid.UUID,
) -> dict:
    work_date = date.today() - timedelta(days=1)
    return {
        "work_date": str(work_date),
        "start_at": _timestamp(8),
        "end_at": _timestamp(16),
        "break_minutes": 0,
        "regular_hours": "8.00",
        "overtime_hours": "0.00",
        "double_time_hours": "0.00",
        "travel_hours": "0.00",
        "leave_hours": "0.00",
        "indirect_hours": "0.00",
        "uncompensated_overtime_hours": "0.00",
        "project_id": str(project_id),
        "schedule_assignment_id": str(assignment_id),
        "charge_code": "DIRECT-PROJECT",
        "cost_code": "01-100",
        "labor_category": "CARPENTER",
        "trade": "Carpentry",
        "location": "Test project site",
        "description": "Mobilization, layout, and site protection",
        "source": "OFFLINE",
        "client_operation_id": str(operation_id),
        "device_id": "test-field-device",
        "original_device_timestamp": datetime.now(UTC).isoformat(),
    }


def _timestamp(hour: int) -> str:
    work_date = date.today() - timedelta(days=1)
    return datetime.combine(work_date, time(hour=hour), tzinfo=UTC).isoformat()


def _principal(tenant_id: uuid.UUID, permissions: frozenset[str]) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        session_id=uuid.uuid4(),
        permissions=permissions,
    )


def _client(principal: Principal) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benson-ai",
        headers={"Authorization": f"Bearer {create_access_token(principal)}"},
    )


async def _seed(
    employee_principal: Principal,
    supervisor: Principal,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    project_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    schedule_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    assignment_id = uuid.uuid4()
    tenant_id = employee_principal.tenant_id
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=tenant_id,
                name="Timekeeping Test",
                slug=f"timekeeping-test-{tenant_id}",
            )
        )
        await set_tenant_context(session, tenant_id)
        for principal in (employee_principal, supervisor):
            session.add(
                LoginSession(
                    id=principal.session_id,
                    tenant_id=tenant_id,
                    user_id=principal.user_id,
                    refresh_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        session.add(
            Project(
                id=project_id,
                tenant_id=tenant_id,
                created_by=supervisor.user_id,
                updated_by=supervisor.user_id,
                proposal_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                property_id=uuid.uuid4(),
                project_number="P-TIME",
                name="Timekeeping Project",
            )
        )
        session.add(
            Employee(
                id=employee_id,
                tenant_id=tenant_id,
                created_by=supervisor.user_id,
                updated_by=supervisor.user_id,
                employee_number="E-TIME",
                first_name="Ada",
                last_name="Builder",
                personal_email="ada-time@example.com",
                company_username="ada.time",
                hire_date=date.today() - timedelta(days=30),
                status=EmployeeStatus.ACTIVE,
                user_id=employee_principal.user_id,
            )
        )
        await session.flush()
        session.add(
            Schedule(
                id=schedule_id,
                tenant_id=tenant_id,
                created_by=supervisor.user_id,
                updated_by=supervisor.user_id,
                project_id=project_id,
                name="Timekeeping Schedule",
                timezone="UTC",
            )
        )
        await session.flush()
        session.add(
            ScheduleActivity(
                id=activity_id,
                tenant_id=tenant_id,
                created_by=supervisor.user_id,
                updated_by=supervisor.user_id,
                schedule_id=schedule_id,
                project_id=project_id,
                title="Mobilization",
                start_at=datetime.fromisoformat(_timestamp(8)),
                end_at=datetime.fromisoformat(_timestamp(16)),
            )
        )
        await session.flush()
        session.add(
            ScheduleAssignment(
                id=assignment_id,
                tenant_id=tenant_id,
                created_by=supervisor.user_id,
                updated_by=supervisor.user_id,
                activity_id=activity_id,
                employee_id=employee_id,
            )
        )
    return project_id, employee_id, assignment_id


async def _assert_history_and_isolation(
    tenant_id: uuid.UUID,
    entry_id: uuid.UUID,
) -> None:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        entry = await session.get(TimeEntry, entry_id)
        assert entry is not None
        assert entry.status is TimeEntryStatus.APPROVED
        assert entry.description == "Mobilization, layout, and site protection"
        actions = set(
            await session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.record_id == entry_id,
                )
            )
        )
        assert actions == {"created", "employee_certified", "supervisor_approved"}
    async with SessionFactory() as other_tenant:
        await set_tenant_context(other_tenant, uuid.uuid4())
        assert await other_tenant.get(TimeEntry, entry_id) is None


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        for model in (
            InboxReceipt,
            TimeCorrection,
            TimeEntry,
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
