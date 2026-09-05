import csv
import io
import json
import os
import uuid
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from xml.etree import ElementTree

import pytest
from app.core.database import SessionFactory
from app.core.security import Principal, create_access_token
from app.core.tenancy import set_tenant_context
from app.main import app
from app.modules.payroll import service as payroll_service
from app.modules.payroll.models import (
    EmployeePayRate,
    PayrollExport,
    PayrollExportLine,
    PayrollJobCost,
    PayrollPeriod,
    PayrollProviderMapping,
    PayrollReconciliationException,
    PayrollResultImport,
    PayrollResultLine,
)
from app.modules.people.models import Employee, EmployeeStatus
from app.modules.platform.models import (
    AuditEvent,
    LoginSession,
    Organization,
    OutboxEvent,
)
from app.modules.projects.models import Project
from app.modules.timekeeping.models import TimeEntry, TimeEntrySource, TimeEntryStatus
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


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_immutable(
        self,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        del content_type
        if key in self.objects:
            raise FileExistsError(key)
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def signed_get_url(self, key: str, expires_seconds: int) -> None:
        del key, expires_seconds


async def test_payroll_preview_lock_and_immutable_multi_format_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    employee_user_id = uuid.uuid4()
    admin = _principal(
        tenant_id,
        frozenset(
            {
                "payroll.periods_manage",
                "payroll.review",
                "payroll.export",
                "payroll.import",
                "payroll.reconcile",
                "payroll.view_wages",
                "payroll.mappings_manage",
                "time.approve_team",
            }
        ),
    )
    employee_id, project_id, approved_id, certified_id = await _seed(
        tenant_id,
        admin,
        employee_user_id,
    )
    storage = MemoryStorage()
    monkeypatch.setattr(payroll_service, "get_object_storage", lambda: storage)
    try:
        async with _client(admin) as client:
            period_response = await client.post(
                "/api/v1/payroll/periods",
                json={
                    "period_start": str(date.today() - timedelta(days=2)),
                    "period_end": str(date.today() - timedelta(days=1)),
                    "pay_date": str(date.today() + timedelta(days=3)),
                    "workweek_definition": "MONDAY_START",
                    "provider": "ADP",
                },
            )
            assert period_response.status_code == 201, period_response.text
            period = period_response.json()
            preview = (
                await client.get(f"/api/v1/payroll/periods/{period['id']}/preview")
            ).json()
            assert preview["ready_to_lock"] is False
            codes = {item["code"] for item in preview["exceptions"]}
            assert "UNAPPROVED_TIME" in codes
            assert "MISSING_EMPLOYEE_MAPPING" in codes
            assert "MISSING_PAY_RATE" in codes
            period = await _advance(client, period, "EMPLOYEE_REVIEW")
            period = await _advance(client, period, "SUPERVISOR_REVIEW")
            period = await _advance(client, period, "PAYROLL_REVIEW")
            blocked_lock = await client.post(
                f"/api/v1/payroll/periods/{period['id']}/transitions",
                headers={"If-Match": str(period["version"])},
                json={
                    "target_status": "LOCKED",
                    "reason": "Attempted lock before payroll exceptions were resolved",
                },
            )
            assert blocked_lock.status_code == 409
            assert blocked_lock.json()["detail"]["message"] == (
                "Payroll period has blocking exceptions"
            )

            await _configure_payroll(client, employee_id, project_id)
            approved = await client.post(
                f"/api/v1/time-entries/{certified_id}/approve",
                headers={"If-Match": "2"},
                json={"reason": "Payroll supervisor verified source time"},
            )
            assert approved.status_code == 200, approved.text
            ready = (
                await client.get(f"/api/v1/payroll/periods/{period['id']}/preview")
            ).json()
            assert ready["ready_to_lock"] is True
            assert ready["approved_entry_count"] == 2
            assert ready["totals"]["regular_hours"] == "12.00"
            assert ready["totals"]["overtime_hours"] == "2.00"
            assert ready["totals"]["estimated_gross_labor"] == "375.00"
            assert set(ready["employees"][0]["source_time_entry_ids"]) == {
                str(approved_id),
                str(certified_id),
            }

            period = await _advance(client, period, "LOCKED")
            assert period["locked_at"] is not None
            assert period["validation_snapshot"]["ready_to_lock"] is True

            exports = []
            for export_format in ("CSV", "XLSX", "JSON"):
                response = await client.post(
                    f"/api/v1/payroll/periods/{period['id']}/exports",
                    headers={"If-Match": str(period["version"])},
                    json={
                        "format": export_format,
                        "include_sensitive_fields": True,
                    },
                )
                assert response.status_code == 201, response.text
                payroll_export = response.json()
                exports.append(payroll_export)
                period["version"] += 1
                download = await client.get(
                    f"/api/v1/payroll/exports/{payroll_export['id']}/download"
                )
                assert download.status_code == 200
                assert download.headers["etag"] == f'"{payroll_export["file_checksum"]}"'
                assert len(download.content) > 100

            listed_exports = (
                await client.get(
                    f"/api/v1/payroll/periods/{period['id']}/exports"
                )
            ).json()
            assert {item["id"] for item in listed_exports} == {
                item["id"] for item in exports
            }
            assert len((await client.get("/api/v1/payroll/pay-rates")).json()) == 1
            assert len((await client.get("/api/v1/payroll/mappings?provider=ADP")).json()) == 6

            assert exports[0]["totals_snapshot"]["totals"] == exports[1][
                "totals_snapshot"
            ]["totals"]
            assert exports[1]["totals_snapshot"]["totals"] == exports[2][
                "totals_snapshot"
            ]["totals"]
            csv_rows = list(
                csv.DictReader(
                    io.StringIO(_export_content(storage, exports[0]).decode())
                )
            )
            assert sum(Decimal(row["regular_hours"]) for row in csv_rows) == Decimal(
                "12.00"
            )
            json_rows = json.loads(_export_content(storage, exports[2]))
            assert sum(Decimal(row["overtime_hours"]) for row in json_rows) == Decimal(
                "2.00"
            )
            xlsx_rows = _xlsx_rows(_export_content(storage, exports[1]))
            assert sum(Decimal(row["regular_hours"]) for row in xlsx_rows) == Decimal(
                "12.00"
            )
            assert sum(Decimal(row["overtime_hours"]) for row in xlsx_rows) == Decimal(
                "2.00"
            )
            assert {row["regular_earning_code"] for row in xlsx_rows} == {"REG"}
            assert {row["period_start"] for row in xlsx_rows} == {
                str(date.today() - timedelta(days=2))
            }

            duplicate = await client.post(
                f"/api/v1/payroll/periods/{period['id']}/exports",
                headers={"If-Match": str(period["version"])},
                json={"format": "CSV", "include_sensitive_fields": True},
            )
            assert duplicate.status_code == 409

            import_payload = {
                    "payroll_export_id": exports[0]["id"],
                    "provider_reference": f"ADP-PAYROLL-{period['id']}",
                    "lines": [
                        _provider_result_line(
                            approved_id,
                            employee_id,
                            date.today() - timedelta(days=1),
                            regular="8.00",
                            overtime="2.00",
                            gross="276.00",
                            net="230.00",
                            employer_taxes="20.00",
                            employer_benefits="10.00",
                            workers_compensation="5.00",
                            fringe_benefits="12.00",
                        ),
                        _provider_result_line(
                            certified_id,
                            employee_id,
                            date.today() - timedelta(days=2),
                            regular="4.00",
                            overtime="0.00",
                            gross="100.00",
                            net="85.00",
                            employer_taxes="8.00",
                            employer_benefits="4.00",
                            workers_compensation="2.00",
                            fringe_benefits="4.00",
                        ),
                    ]
            }
            result_import = await client.post(
                f"/api/v1/payroll/periods/{period['id']}/result-imports",
                headers={"If-Match": str(period["version"])},
                json=import_payload,
            )
            assert result_import.status_code == 201, result_import.text
            imported = result_import.json()
            assert imported["status"] == "EXCEPTIONS"
            assert len(imported["source_checksum"]) == 64
            retry = await client.post(
                f"/api/v1/payroll/periods/{period['id']}/result-imports",
                headers={"If-Match": str(period["version"])},
                json=import_payload,
            )
            assert retry.status_code == 201
            assert retry.json()["id"] == imported["id"]
            reconciliation = (
                await client.get(
                    f"/api/v1/payroll/result-imports/{imported['id']}/reconciliation"
                )
            ).json()
            assert [item["code"] for item in reconciliation["exceptions"]] == [
                "GROSS_WAGE_MISMATCH"
            ]
            blocked = await client.post(
                f"/api/v1/payroll/result-imports/{imported['id']}/reconcile",
                headers={"If-Match": str(imported["version"])},
            )
            assert blocked.status_code == 409
            exception = reconciliation["exceptions"][0]
            resolved = await client.post(
                f"/api/v1/payroll/reconciliation-exceptions/{exception['id']}/resolve",
                headers={"If-Match": str(exception["version"])},
                json={
                    "reason": (
                        "Payroll administrator verified the provider rounding "
                        "difference against the pay register."
                    )
                },
            )
            assert resolved.status_code == 200, resolved.text
            reconciled = await client.post(
                f"/api/v1/payroll/result-imports/{imported['id']}/reconcile",
                headers={"If-Match": str(imported["version"])},
            )
            assert reconciled.status_code == 200, reconciled.text
            assert reconciled.json()["status"] == "RECONCILED"
            final_reconciliation = (
                await client.get(
                    f"/api/v1/payroll/result-imports/{imported['id']}/reconciliation"
                )
            ).json()
            assert final_reconciliation["job_cost_count"] == 2
            assert final_reconciliation["job_cost_total"] == "441.00"

        hidden_wages = _principal(
            tenant_id,
            frozenset({"payroll.review", "payroll.export"}),
        )
        await _add_session(tenant_id, hidden_wages)
        async with _client(hidden_wages) as client:
            hidden = (
                await client.get(f"/api/v1/payroll/periods/{period['id']}/preview")
            ).json()
            assert hidden["totals"]["estimated_gross_labor"] is None
            assert hidden["employees"][0]["estimated_gross_labor"] is None
            listed = (await client.get("/api/v1/payroll/periods")).json()
            locked_snapshot = listed[0]["validation_snapshot"]
            assert locked_snapshot["totals"]["estimated_gross_labor"] is None
            assert locked_snapshot["employees"][0]["estimated_gross_labor"] is None
            forbidden = await client.get(
                f"/api/v1/payroll/exports/{exports[0]['id']}/download"
            )
            assert forbidden.status_code == 403
            hidden_exports = await client.get(
                f"/api/v1/payroll/periods/{period['id']}/exports"
            )
            assert hidden_exports.status_code == 200
            assert hidden_exports.json() == []

        await _assert_export_snapshots(tenant_id, exports, approved_id)
    finally:
        await _clean_tenant(tenant_id)


async def _configure_payroll(
    client: AsyncClient,
    employee_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    effective = str(date.today() - timedelta(days=30))
    rate = await client.post(
        "/api/v1/payroll/pay-rates",
        json={
            "employee_id": str(employee_id),
            "effective_from": effective,
            "base_rate": "25.0000",
            "overtime_rate": "37.5000",
            "double_time_rate": "50.0000",
            "fringe_rate": "3.0000",
            "cash_in_lieu_rate": "1.0000",
        },
    )
    assert rate.status_code == 201, rate.text
    mappings = (
        ("EMPLOYEE", str(employee_id), "ADP-E-100"),
        ("EARNING", "REGULAR", "REG"),
        ("EARNING", "OVERTIME", "OT"),
        ("PROJECT", str(project_id), "ADP-JOB-1"),
        ("COST_CODE", "01-100", "010100"),
        ("LABOR_CATEGORY", "CARPENTER", "CARP"),
    )
    for mapping_type, internal_key, external_code in mappings:
        response = await client.post(
            "/api/v1/payroll/mappings",
            json={
                "provider": "ADP",
                "mapping_type": mapping_type,
                "internal_key": internal_key,
                "external_code": external_code,
                "effective_from": effective,
            },
        )
        assert response.status_code == 201, response.text


async def _advance(client: AsyncClient, period: dict, target: str) -> dict:
    response = await client.post(
        f"/api/v1/payroll/periods/{period['id']}/transitions",
        headers={"If-Match": str(period["version"])},
        json={
            "target_status": target,
            "reason": f"Verified payroll controls for {target}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _provider_result_line(
    time_entry_id: uuid.UUID,
    employee_id: uuid.UUID,
    work_date: date,
    *,
    regular: str,
    overtime: str,
    gross: str,
    net: str,
    employer_taxes: str,
    employer_benefits: str,
    workers_compensation: str,
    fringe_benefits: str,
) -> dict:
    return {
        "time_entry_id": str(time_entry_id),
        "provider_employee_id": "ADP-E-100",
        "provider_payroll_id": "ADP-RUN-100",
        "payment_reference": f"PAY-{time_entry_id}",
        "work_date": str(work_date),
        "pay_date": str(date.today() + timedelta(days=3)),
        "regular_hours": regular,
        "overtime_hours": overtime,
        "double_time_hours": "0.00",
        "travel_hours": "0.00",
        "leave_hours": "0.00",
        "indirect_hours": "0.00",
        "base_rate": "25.0000",
        "overtime_rate": "37.5000",
        "double_time_rate": "50.0000",
        "gross_wages": gross,
        "employer_taxes": employer_taxes,
        "employee_deductions": "0.00",
        "employer_benefits": employer_benefits,
        "workers_compensation": workers_compensation,
        "fringe_benefits": fringe_benefits,
        "net_pay": net,
        "is_adjustment": False,
    }


def _export_content(storage: MemoryStorage, payroll_export: dict) -> bytes:
    matches = [
        content
        for key, content in storage.objects.items()
        if f"/{payroll_export['id']}/" in key
        and payroll_export["file_checksum"] in key
    ]
    assert len(matches) == 1
    return matches[0]


def _xlsx_rows(content: bytes) -> list[dict[str, str]]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(content)) as workbook:
        root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in root.findall(".//x:row", namespace):
        values = []
        for cell in row.findall("x:c", namespace):
            inline = cell.find("x:is/x:t", namespace)
            number = cell.find("x:v", namespace)
            values.append(inline.text if inline is not None else number.text if number is not None else "")
        rows.append(values)
    headers = rows[0]
    return [dict(zip(headers, values, strict=True)) for values in rows[1:]]


async def _seed(
    tenant_id: uuid.UUID,
    admin: Principal,
    employee_user_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    employee_id = uuid.uuid4()
    project_id = uuid.uuid4()
    approved_id = uuid.uuid4()
    certified_id = uuid.uuid4()
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=tenant_id,
                name="Payroll Test",
                slug=f"payroll-test-{tenant_id}",
            )
        )
        await set_tenant_context(session, tenant_id)
        session.add(
            LoginSession(
                id=admin.session_id,
                tenant_id=tenant_id,
                user_id=admin.user_id,
                refresh_token_hash=uuid.uuid4().hex * 2,
                csrf_token_hash=uuid.uuid4().hex * 2,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add(
            Employee(
                id=employee_id,
                tenant_id=tenant_id,
                created_by=admin.user_id,
                updated_by=admin.user_id,
                employee_number="E-PAY-100",
                first_name="Casey",
                last_name="Carpenter",
                personal_email="casey-payroll@example.com",
                company_username="casey.payroll",
                hire_date=date.today() - timedelta(days=100),
                status=EmployeeStatus.ACTIVE,
                user_id=employee_user_id,
            )
        )
        session.add(
            Project(
                id=project_id,
                tenant_id=tenant_id,
                created_by=admin.user_id,
                updated_by=admin.user_id,
                proposal_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                property_id=uuid.uuid4(),
                project_number="P-PAY-1",
                name="Payroll Test Project",
            )
        )
        session.add_all(
            [
                _time_entry(
                    approved_id,
                    tenant_id,
                    admin.user_id,
                    employee_id,
                    project_id,
                    date.today() - timedelta(days=1),
                    10,
                    TimeEntryStatus.APPROVED,
                ),
                _time_entry(
                    certified_id,
                    tenant_id,
                    admin.user_id,
                    employee_id,
                    project_id,
                    date.today() - timedelta(days=2),
                    4,
                    TimeEntryStatus.CERTIFIED,
                ),
            ]
        )
    return employee_id, project_id, approved_id, certified_id


def _time_entry(
    entry_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    employee_id: uuid.UUID,
    project_id: uuid.UUID,
    work_date: date,
    hours: int,
    status: TimeEntryStatus,
) -> TimeEntry:
    overtime = Decimal("2.00") if hours == 10 else Decimal("0.00")
    return TimeEntry(
        id=entry_id,
        tenant_id=tenant_id,
        created_by=actor_id,
        updated_by=actor_id,
        employee_id=employee_id,
        work_date=work_date,
        start_at=datetime.combine(work_date, time(8), tzinfo=UTC),
        end_at=datetime.combine(work_date, time(8 + hours), tzinfo=UTC),
        break_minutes=0,
        total_hours=Decimal(hours),
        regular_hours=Decimal(hours) - overtime,
        overtime_hours=overtime,
        double_time_hours=0,
        travel_hours=0,
        leave_hours=0,
        indirect_hours=0,
        uncompensated_overtime_hours=0,
        project_id=project_id,
        contract_code="FAKE-CONTRACT-FOR-STRUCTURE",
        task_order="TO-1",
        clin="0001",
        funding_line="FL-1",
        charge_code="DIRECT-PROJECT",
        cost_code="01-100",
        labor_category="CARPENTER",
        description="Approved project labor for payroll verification",
        status=status,
        source=TimeEntrySource.WEB,
        client_operation_id=uuid.uuid4(),
        original_device_timestamp=datetime.now(UTC),
        certified_at=datetime.now(UTC),
        certified_by=employee_id,
        certification_statement="Employee certified all recorded payroll hours.",
        approved_at=datetime.now(UTC) if status is TimeEntryStatus.APPROVED else None,
        approved_by=actor_id if status is TimeEntryStatus.APPROVED else None,
        version=3 if status is TimeEntryStatus.APPROVED else 2,
    )


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


async def _add_session(tenant_id: uuid.UUID, principal: Principal) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        session.add(
            LoginSession(
                id=principal.session_id,
                tenant_id=tenant_id,
                user_id=principal.user_id,
                refresh_token_hash=uuid.uuid4().hex * 2,
                csrf_token_hash=uuid.uuid4().hex * 2,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )


async def _assert_export_snapshots(
    tenant_id: uuid.UUID,
    exports: list[dict],
    source_entry_id: uuid.UUID,
) -> None:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        persisted = list(
            await session.scalars(
                select(PayrollExport).where(PayrollExport.tenant_id == tenant_id)
            )
        )
        assert len(persisted) == 3
        for payroll_export in persisted:
            assert len(payroll_export.file_checksum) == 64
            line = await session.scalar(
                select(PayrollExportLine).where(
                    PayrollExportLine.tenant_id == tenant_id,
                    PayrollExportLine.payroll_export_id == payroll_export.id,
                    PayrollExportLine.time_entry_id == source_entry_id,
                )
            )
            assert line is not None
            assert line.base_rate == Decimal("25.0000")
            assert line.gross_labor == Decimal("275.00")
            assert line.mapping_snapshot["EMPLOYEE:" + str(line.employee_id)]["version"] == 1
            assert line.mapping_snapshot["PAY_RATE"]["version"] == 1
        actions = set(
            await session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.record_type == "PayrollExport",
                )
            )
        )
        assert actions == {"generated"}
        event_count = len(
            list(
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.tenant_id == tenant_id,
                        OutboxEvent.event_type == "PayrollExportGenerated",
                    )
                )
            )
        )
        assert event_count == len(exports)


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        for model in (
            PayrollJobCost,
            PayrollReconciliationException,
            PayrollResultLine,
            PayrollResultImport,
            PayrollExportLine,
            PayrollExport,
            PayrollProviderMapping,
            EmployeePayRate,
            PayrollPeriod,
            TimeEntry,
            Employee,
            Project,
            OutboxEvent,
            AuditEvent,
            LoginSession,
        ):
            await session.execute(delete(model).where(model.tenant_id == tenant_id))
        await session.execute(delete(Organization).where(Organization.id == tenant_id))
