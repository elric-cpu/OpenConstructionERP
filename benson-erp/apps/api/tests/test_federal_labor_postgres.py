import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from app.core.database import SessionFactory
from app.core.security import Principal, create_access_token
from app.core.tenancy import set_tenant_context
from app.main import app
from app.modules.federal_labor.models import (
    EmployeeQualification,
    FederalChargeCode,
    FederalInvoiceSupport,
    FederalInvoiceSupportLine,
    FederalLaborRate,
)
from app.modules.people.models import Employee, EmployeeStatus
from app.modules.platform.models import AuditEvent, LoginSession, Organization, OutboxEvent
from app.modules.projects.models import Project
from app.modules.timekeeping.models import TimeEntry
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="PostgreSQL integration tests disabled",
    ),
]


async def test_federal_time_floor_check_and_immutable_invoice_support() -> None:
    tenant_id = uuid.uuid4()
    employee_user_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    project_id = uuid.uuid4()
    admin = _principal(
        tenant_id,
        {
            "federal_labor.charge_codes_manage",
            "federal_labor.charge_codes_read",
            "federal_labor.floor_check_read",
            "federal_labor.invoice_support_generate",
            "federal_labor.invoice_support_read",
            "federal_labor.qualifications_manage",
            "federal_labor.rates_manage",
            "time.approve_team",
        },
    )
    employee = _principal(
        tenant_id,
        {"federal_labor.charge_codes_read", "time.certify_own", "time.enter_own"},
        user_id=employee_user_id,
    )
    await _seed(tenant_id, employee_id, employee_user_id, project_id, admin, employee)
    try:
        async with _client(admin) as client:
            charge_code = await _create_charge_code(client, project_id)
            await _create_rate_and_qualification(client, charge_code["id"], employee_id)

        work_date = date.today() - timedelta(days=1)
        async with _client(employee) as client:
            mismatch = await client.post(
                "/api/v1/time-entries",
                json=_time_payload(
                    employee_id,
                    charge_code["id"],
                    project_id,
                    work_date,
                    contract_code="WRONG-CONTRACT",
                ),
            )
            assert mismatch.status_code == 409
            assert "canonical federal charge code" in mismatch.json()["detail"]

            created_response = await client.post(
                "/api/v1/time-entries",
                json=_time_payload(
                    employee_id,
                    charge_code["id"],
                    project_id,
                    work_date,
                ),
            )
            assert created_response.status_code == 201, created_response.text
            entry = created_response.json()
            assert entry["contract_code"] == "FA-2026-001"
            assert entry["task_order"] == "TO-01"
            assert entry["clin"] == "0001"
            assert entry["charge_code"] == "FA-TO1-CARP"
            assert entry["labor_category"] == "CARPENTER"

        async with _client(admin) as client:
            draft_floor_check = await client.get(
                "/api/v1/federal-labor/floor-check",
                params={
                    "period_start": str(work_date),
                    "period_end": str(work_date),
                },
            )
            assert draft_floor_check.status_code == 200
            draft_row = draft_floor_check.json()["entries"][0]
            assert draft_row["time_entry_status"] == "DRAFT"
            assert draft_row["approved_by"] is None
            assert draft_row["payroll_status"] == "NOT_PAID"

        async with _client(employee) as client:
            certified_response = await client.post(
                f"/api/v1/time-entries/{entry['id']}/certify",
                headers={"If-Match": str(entry["version"])},
                json={"statement": "I certify that this federal time entry is complete."},
            )
            assert certified_response.status_code == 200, certified_response.text
            certified = certified_response.json()

        async with _client(admin) as client:
            approved_response = await client.post(
                f"/api/v1/time-entries/{entry['id']}/approve",
                headers={"If-Match": str(certified["version"])},
                json={"reason": "Supervisor verified the federal labor allocation."},
            )
            assert approved_response.status_code == 200, approved_response.text

            request = {
                "contract_code": "FA-2026-001",
                "task_order": "TO-01",
                "invoice_number": "INV-FED-001",
                "invoice_period_start": str(work_date),
                "invoice_period_end": str(work_date),
            }
            preview_response = await client.post(
                "/api/v1/federal-labor/invoice-support/preview",
                json=request,
            )
            assert preview_response.status_code == 200, preview_response.text
            preview = preview_response.json()
            assert preview["ready"] is True
            assert preview["total_approved_hours"] == "10.00"
            assert preview["total_extended_amount"] == "1200.00"
            assert preview["lines"][0]["regular_hours"] == "8.00"
            assert preview["lines"][0]["overtime_hours"] == "1.00"
            assert preview["lines"][0]["double_time_hours"] == "1.00"
            assert preview["lines"][0]["regular_bill_rate"] == "100.0000"
            assert preview["lines"][0]["overtime_bill_rate"] == "150.0000"
            assert preview["lines"][0]["double_time_bill_rate"] == "250.0000"
            assert preview["lines"][0]["payroll_reconciliation_status"] == "NOT_IMPORTED"

            generated_response = await client.post(
                "/api/v1/federal-labor/invoice-support",
                json=request,
            )
            assert generated_response.status_code == 201, generated_response.text
            generated = generated_response.json()
            assert generated["artifact_version"] == 1
            assert len(generated["content_checksum"]) == 64
            assert generated["source_snapshot"]["calculation"]["extended_amount"]

            duplicate = await client.post(
                "/api/v1/federal-labor/invoice-support",
                json=request,
            )
            assert duplicate.status_code == 409

            floor_check = await client.get(
                "/api/v1/federal-labor/floor-check",
                params={
                    "period_start": str(work_date),
                    "period_end": str(work_date),
                    "contract_code": "FA-2026-001",
                },
            )
            row = floor_check.json()["entries"][0]
            assert row["time_entry_status"] == "APPROVED"
            assert row["payroll_status"] == "NOT_PAID"
            assert row["invoice_status"] == "INVOICED"

        other = _principal(
            uuid.uuid4(),
            {
                "federal_labor.charge_codes_read",
                "federal_labor.invoice_support_read",
            },
        )
        await _seed_other_tenant(other)
        async with _client(other) as client:
            hidden = await client.get(
                f"/api/v1/federal-labor/invoice-support/{generated['id']}"
            )
            assert hidden.status_code == 404
    finally:
        await _clean_tenant(tenant_id)
        if "other" in locals():
            await _clean_tenant(other.tenant_id)


async def _create_charge_code(client: AsyncClient, project_id: uuid.UUID) -> dict:
    response = await client.post(
        "/api/v1/federal-labor/charge-codes",
        json={
            "code": "FA-TO1-CARP",
            "name": "Federal carpenter labor",
            "profile": "FEDERAL_TIME_AND_MATERIALS",
            "agency_code": "GSA",
            "contract_code": "FA-2026-001",
            "task_order": "TO-01",
            "clin": "0001",
            "funding_line": "FL-01",
            "project_id": str(project_id),
            "cost_code": "01-100",
            "labor_category": "CARPENTER",
            "active_from": str(date.today() - timedelta(days=30)),
            "required_qualification_code": "CARP-JOURNEY",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_rate_and_qualification(
    client: AsyncClient,
    charge_code_id: str,
    employee_id: uuid.UUID,
) -> None:
    effective = str(date.today() - timedelta(days=30))
    rate = await client.post(
        "/api/v1/federal-labor/rates",
        json={
            "federal_charge_code_id": charge_code_id,
            "labor_category": "CARPENTER",
            "effective_from": effective,
            "regular_bill_rate": "100.0000",
            "overtime_bill_rate": "150.0000",
            "double_time_bill_rate": "250.0000",
            "currency": "USD",
            "source_reference": "Contract FA-2026-001 rate schedule",
        },
    )
    assert rate.status_code == 201, rate.text
    qualification = await client.post(
        "/api/v1/federal-labor/qualifications",
        json={
            "employee_id": str(employee_id),
            "qualification_code": "CARP-JOURNEY",
            "qualification_name": "Journey Carpenter",
            "effective_from": effective,
            "status": "ACTIVE",
            "issuer": "Benson qualification review",
        },
    )
    assert qualification.status_code == 201, qualification.text


def _time_payload(
    employee_id: uuid.UUID,
    charge_code_id: str,
    project_id: uuid.UUID,
    work_date: date,
    *,
    contract_code: str | None = None,
) -> dict:
    start = datetime.combine(work_date, datetime.min.time(), tzinfo=UTC).replace(hour=7)
    return {
        "employee_id": str(employee_id),
        "work_date": str(work_date),
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=10)).isoformat(),
        "break_minutes": 0,
        "regular_hours": "8.00",
        "overtime_hours": "1.00",
        "double_time_hours": "1.00",
        "project_id": str(project_id),
        "federal_charge_code_id": charge_code_id,
        "contract_code": contract_code,
        "charge_code": "FA-TO1-CARP",
        "description": "Carpentry work under federal task order TO-01.",
        "location": "Federal project work area",
        "source": "WEB",
        "client_operation_id": str(uuid.uuid4()),
        "original_device_timestamp": datetime.now(UTC).isoformat(),
    }


def _principal(
    tenant_id: uuid.UUID,
    permissions: set[str],
    *,
    user_id: uuid.UUID | None = None,
) -> Principal:
    return Principal(
        user_id=user_id or uuid.uuid4(),
        tenant_id=tenant_id,
        session_id=uuid.uuid4(),
        permissions=frozenset(permissions),
    )


def _client(principal: Principal) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benson-ai",
        headers={"Authorization": f"Bearer {create_access_token(principal)}"},
    )


async def _seed(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    employee_user_id: uuid.UUID,
    project_id: uuid.UUID,
    *principals: Principal,
) -> None:
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=tenant_id,
                name="Federal Labor Test",
                slug=f"federal-labor-{tenant_id}",
            )
        )
        await set_tenant_context(session, tenant_id)
        for principal in principals:
            session.add(_login_session(principal))
        session.add(
            Employee(
                id=employee_id,
                tenant_id=tenant_id,
                created_by=principals[0].user_id,
                updated_by=principals[0].user_id,
                employee_number="E-FED-100",
                first_name="Riley",
                last_name="Carpenter",
                personal_email="riley-federal@example.com",
                company_username="riley.federal",
                hire_date=date.today() - timedelta(days=365),
                status=EmployeeStatus.ACTIVE,
                user_id=employee_user_id,
            )
        )
        session.add(
            Project(
                id=project_id,
                tenant_id=tenant_id,
                created_by=principals[0].user_id,
                updated_by=principals[0].user_id,
                proposal_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                property_id=uuid.uuid4(),
                project_number="P-FED-1",
                name="Federal Labor Test Project",
            )
        )


async def _seed_other_tenant(principal: Principal) -> None:
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=principal.tenant_id,
                name="Other Federal Tenant",
                slug=f"other-federal-{principal.tenant_id}",
            )
        )
        await set_tenant_context(session, principal.tenant_id)
        session.add(_login_session(principal))


def _login_session(principal: Principal) -> LoginSession:
    return LoginSession(
        id=principal.session_id,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        refresh_token_hash=uuid.uuid4().hex * 2,
        csrf_token_hash=uuid.uuid4().hex * 2,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    owner_url = os.environ.get("TEST_DATABASE_OWNER_URL")
    if owner_url is None:
        raise RuntimeError("TEST_DATABASE_OWNER_URL is required for immutable test cleanup")
    owner_engine = create_async_engine(owner_url)
    owner_sessions = async_sessionmaker(owner_engine, expire_on_commit=False)
    async with owner_sessions() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        await session.execute(
            text(
                "ALTER TABLE federal_invoice_support_lines "
                "DISABLE TRIGGER federal_invoice_support_lines_immutable"
            )
        )
        await session.execute(
            text(
                "ALTER TABLE federal_invoice_support "
                "DISABLE TRIGGER federal_invoice_support_immutable"
            )
        )
        for model in (
            FederalInvoiceSupportLine,
            FederalInvoiceSupport,
            FederalLaborRate,
            EmployeeQualification,
            TimeEntry,
            FederalChargeCode,
            Employee,
            Project,
            OutboxEvent,
            AuditEvent,
            LoginSession,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Organization).where(Organization.id == tenant_id))
        await session.execute(
            text(
                "ALTER TABLE federal_invoice_support_lines "
                "ENABLE TRIGGER federal_invoice_support_lines_immutable"
            )
        )
        await session.execute(
            text(
                "ALTER TABLE federal_invoice_support "
                "ENABLE TRIGGER federal_invoice_support_immutable"
            )
        )
    await owner_engine.dispose()
