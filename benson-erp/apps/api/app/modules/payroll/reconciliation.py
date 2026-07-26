import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.payroll.events import PAYROLL_RECONCILED, PAYROLL_RESULTS_IMPORTED
from app.modules.payroll.models import (
    PayrollExport,
    PayrollExportLine,
    PayrollExportStatus,
    PayrollJobCost,
    PayrollPeriod,
    PayrollPeriodExportStatus,
    PayrollPeriodStatus,
    PayrollReconciliationException,
    PayrollReconciliationStatus,
    PayrollResultImport,
    PayrollResultImportStatus,
    PayrollResultLine,
    ReconciliationExceptionStatus,
)
from app.modules.payroll.permissions import (
    PAYROLL_IMPORT,
    PAYROLL_RECONCILE,
    PAYROLL_VIEW_WAGES,
)
from app.modules.payroll.schemas import (
    PayrollReconciliationExceptionRead,
    PayrollReconciliationRead,
    PayrollResultImportCreate,
    PayrollResultImportRead,
)
from app.modules.platform.audit import add_audit, add_outbox

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HOUR_FIELDS = (
    "regular_hours",
    "overtime_hours",
    "double_time_hours",
    "travel_hours",
    "leave_hours",
    "indirect_hours",
)
RATE_FIELDS = ("base_rate", "overtime_rate", "double_time_rate")


async def import_results(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
    expected_version: int,
    data: PayrollResultImportCreate,
) -> PayrollResultImport:
    principal.require(PAYROLL_IMPORT)
    principal.require(PAYROLL_VIEW_WAGES)
    period = await _period(session, principal, period_id, for_update=True)
    payroll_export = await session.scalar(
        select(PayrollExport).where(
            PayrollExport.tenant_id == principal.tenant_id,
            PayrollExport.id == data.payroll_export_id,
            PayrollExport.payroll_period_id == period.id,
        )
    )
    if payroll_export is None:
        raise HTTPException(status_code=404, detail="Payroll export not found for period")
    source_checksum = _source_checksum(data)
    existing = await session.scalar(
        select(PayrollResultImport).where(
            PayrollResultImport.tenant_id == principal.tenant_id,
            (
                (PayrollResultImport.payroll_export_id == payroll_export.id)
                | (
                    (PayrollResultImport.provider == period.provider)
                    & (
                        PayrollResultImport.provider_reference
                        == data.provider_reference.strip()
                    )
                )
            ),
        )
    )
    if existing:
        if (
            existing.payroll_export_id == payroll_export.id
            and existing.provider_reference == data.provider_reference.strip()
            and existing.source_checksum == source_checksum
        ):
            return existing
        raise HTTPException(status_code=409, detail="Duplicate payroll result import")
    if period.version != expected_version:
        raise HTTPException(status_code=409, detail="Payroll period version conflict")
    if period.status is not PayrollPeriodStatus.EXPORTED:
        raise HTTPException(status_code=409, detail="Payroll period must be exported")
    export_lines = list(
        await session.scalars(
            select(PayrollExportLine).where(
                PayrollExportLine.tenant_id == principal.tenant_id,
                PayrollExportLine.payroll_export_id == payroll_export.id,
            )
        )
    )
    export_index = {line.time_entry_id: line for line in export_lines}
    unknown = [line.time_entry_id for line in data.lines if line.time_entry_id not in export_index]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Provider results contain {len(unknown)} unknown time entries",
        )
    imported = PayrollResultImport(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        payroll_period_id=period.id,
        payroll_export_id=payroll_export.id,
        provider=period.provider,
        provider_reference=data.provider_reference.strip(),
        source_checksum=source_checksum,
        imported_at=datetime.now(UTC),
        imported_by=principal.user_id,
    )
    session.add(imported)
    await session.flush()
    result_by_entry: dict[uuid.UUID, PayrollResultLine] = {}
    exceptions: list[PayrollReconciliationException] = []
    for item in data.lines:
        export_line = export_index[item.time_entry_id]
        result_line = PayrollResultLine(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            payroll_result_import_id=imported.id,
            payroll_export_line_id=export_line.id,
            employee_id=export_line.employee_id,
            **item.model_dump(),
        )
        session.add(result_line)
        await session.flush()
        result_by_entry[item.time_entry_id] = result_line
        exceptions.extend(
            _compare_line(
                principal,
                imported.id,
                export_line,
                result_line,
                period.pay_date,
            )
        )
    for export_line in export_lines:
        if export_line.time_entry_id not in result_by_entry:
            exceptions.append(
                _exception(
                    principal,
                    imported.id,
                    None,
                    "APPROVED_HOURS_NOT_PAID",
                    f"No provider result for time entry {export_line.time_entry_id}",
                    str(export_line.time_entry_id),
                    None,
                )
            )
    session.add_all(exceptions)
    imported.status = (
        PayrollResultImportStatus.EXCEPTIONS
        if exceptions
        else PayrollResultImportStatus.IMPORTED
    )
    imported.reconciliation_summary = _summary(data, exceptions)
    period.status = PayrollPeriodStatus.PROCESSED
    period.export_status = PayrollPeriodExportStatus.PROCESSED
    period.reconciliation_status = (
        PayrollReconciliationStatus.EXCEPTIONS
        if exceptions
        else PayrollReconciliationStatus.IN_PROGRESS
    )
    period.updated_by = principal.user_id
    period.version += 1
    payroll_export.status = PayrollExportStatus.ACKNOWLEDGED
    payroll_export.provider_reference = imported.provider_reference
    payroll_export.acknowledged_at = datetime.now(UTC)
    payroll_export.updated_by = principal.user_id
    payroll_export.version += 1
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "PayrollResultImport",
        imported.id,
        "imported",
        correlation_id,
        None,
        {
            "provider": imported.provider,
            "provider_reference": imported.provider_reference,
            "source_checksum": imported.source_checksum,
            "line_count": len(data.lines),
            "exception_count": len(exceptions),
        },
    )
    add_outbox(
        session,
        principal,
        PAYROLL_RESULTS_IMPORTED,
        "PayrollResultImport",
        imported.id,
        correlation_id,
        f"payroll-results-imported:{imported.id}",
        {
            "payroll_result_import_id": str(imported.id),
            "payroll_period_id": str(period.id),
            "exception_count": len(exceptions),
        },
    )
    await session.commit()
    return imported


async def get_reconciliation(
    session: AsyncSession,
    principal: Principal,
    import_id: uuid.UUID,
) -> PayrollReconciliationRead:
    principal.require(PAYROLL_RECONCILE)
    principal.require(PAYROLL_VIEW_WAGES)
    imported = await _result_import(session, principal, import_id)
    exceptions = list(
        await session.scalars(
            select(PayrollReconciliationException)
            .where(
                PayrollReconciliationException.tenant_id == principal.tenant_id,
                PayrollReconciliationException.payroll_result_import_id == imported.id,
            )
            .order_by(PayrollReconciliationException.created_at)
        )
    )
    cost_count, cost_total = (
        await session.execute(
            select(func.count(PayrollJobCost.id), func.coalesce(func.sum(PayrollJobCost.total_cost), 0))
            .join(
                PayrollResultLine,
                and_(
                    PayrollResultLine.tenant_id == PayrollJobCost.tenant_id,
                    PayrollResultLine.id == PayrollJobCost.payroll_result_line_id,
                ),
            )
            .where(
                PayrollJobCost.tenant_id == principal.tenant_id,
                PayrollResultLine.payroll_result_import_id == imported.id,
            )
        )
    ).one()
    return PayrollReconciliationRead(
        result_import=PayrollResultImportRead.model_validate(imported),
        exceptions=[
            PayrollReconciliationExceptionRead.model_validate(item)
            for item in exceptions
        ],
        job_cost_count=cost_count,
        job_cost_total=cost_total,
        calculation={
            "job_cost": (
                "gross_wages + employer_taxes + employer_benefits "
                "+ workers_compensation + fringe_benefits"
            ),
            "source": "Imported provider results linked to immutable payroll export lines",
        },
    )


async def list_result_imports(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
) -> list[PayrollResultImport]:
    principal.require(PAYROLL_RECONCILE)
    principal.require(PAYROLL_VIEW_WAGES)
    await _period(session, principal, period_id)
    return list(
        await session.scalars(
            select(PayrollResultImport)
            .where(
                PayrollResultImport.tenant_id == principal.tenant_id,
                PayrollResultImport.payroll_period_id == period_id,
            )
            .order_by(PayrollResultImport.imported_at.desc())
        )
    )


async def resolve_exception(
    session: AsyncSession,
    principal: Principal,
    exception_id: uuid.UUID,
    expected_version: int,
    reason: str,
) -> PayrollReconciliationException:
    principal.require(PAYROLL_RECONCILE)
    item = await session.scalar(
        select(PayrollReconciliationException)
        .where(
            PayrollReconciliationException.tenant_id == principal.tenant_id,
            PayrollReconciliationException.id == exception_id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Reconciliation exception not found")
    if item.version != expected_version:
        raise HTTPException(status_code=409, detail="Exception version conflict")
    if item.status is ReconciliationExceptionStatus.RESOLVED:
        raise HTTPException(status_code=409, detail="Exception is already resolved")
    item.status = ReconciliationExceptionStatus.RESOLVED
    item.resolution_reason = reason
    item.resolved_at = datetime.now(UTC)
    item.resolved_by = principal.user_id
    item.updated_by = principal.user_id
    item.version += 1
    add_audit(
        session,
        principal,
        "PayrollReconciliationException",
        item.id,
        "resolved",
        correlation_uuid(),
        {"status": "OPEN"},
        {"status": "RESOLVED"},
        reason,
    )
    await session.commit()
    return item


async def reconcile(
    session: AsyncSession,
    principal: Principal,
    import_id: uuid.UUID,
    expected_version: int,
) -> PayrollResultImport:
    principal.require(PAYROLL_RECONCILE)
    principal.require(PAYROLL_VIEW_WAGES)
    imported = await _result_import(session, principal, import_id, for_update=True)
    if imported.version != expected_version:
        raise HTTPException(status_code=409, detail="Payroll result version conflict")
    if imported.status is PayrollResultImportStatus.RECONCILED:
        raise HTTPException(status_code=409, detail="Payroll result is already reconciled")
    open_count = await session.scalar(
        select(func.count(PayrollReconciliationException.id)).where(
            PayrollReconciliationException.tenant_id == principal.tenant_id,
            PayrollReconciliationException.payroll_result_import_id == imported.id,
            PayrollReconciliationException.status == ReconciliationExceptionStatus.OPEN,
        )
    )
    if open_count:
        raise HTTPException(
            status_code=409,
            detail=f"Payroll reconciliation has {open_count} open exceptions",
        )
    rows = list(
        (
            await session.execute(
                select(PayrollResultLine, PayrollExportLine)
                .join(
                    PayrollExportLine,
                    and_(
                        PayrollExportLine.tenant_id == PayrollResultLine.tenant_id,
                        PayrollExportLine.id
                        == PayrollResultLine.payroll_export_line_id,
                    ),
                )
                .where(
                    PayrollResultLine.tenant_id == principal.tenant_id,
                    PayrollResultLine.payroll_result_import_id == imported.id,
                )
            )
        ).tuples()
    )
    costs = []
    for result, exported in rows:
        if exported.project_id is None:
            continue
        total = (
            result.gross_wages
            + result.employer_taxes
            + result.employer_benefits
            + result.workers_compensation
            + result.fringe_benefits
        ).quantize(CENT)
        costs.append(
            PayrollJobCost(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                updated_by=principal.user_id,
                payroll_result_line_id=result.id,
                project_id=exported.project_id,
                cost_code=exported.cost_code,
                transaction_date=result.pay_date,
                direct_wages=result.gross_wages,
                employer_taxes=result.employer_taxes,
                employer_benefits=result.employer_benefits,
                workers_compensation=result.workers_compensation,
                fringe_benefits=result.fringe_benefits,
                total_cost=total,
                calculation_snapshot={
                    "formula": (
                        "gross_wages + employer_taxes + employer_benefits "
                        "+ workers_compensation + fringe_benefits"
                    ),
                    "source_result_line_id": str(result.id),
                },
            )
        )
    session.add_all(costs)
    period = await _period(session, principal, imported.payroll_period_id, for_update=True)
    imported.status = PayrollResultImportStatus.RECONCILED
    imported.reconciled_at = datetime.now(UTC)
    imported.reconciled_by = principal.user_id
    imported.updated_by = principal.user_id
    imported.version += 1
    imported.reconciliation_summary = {
        **(imported.reconciliation_summary or {}),
        "job_cost_count": len(costs),
        "job_cost_total": str(sum((item.total_cost for item in costs), ZERO)),
    }
    period.status = PayrollPeriodStatus.RECONCILED
    period.reconciliation_status = PayrollReconciliationStatus.RECONCILED
    period.updated_by = principal.user_id
    period.version += 1
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "PayrollResultImport",
        imported.id,
        "reconciled",
        correlation_id,
        None,
        {
            "status": "RECONCILED",
            "job_cost_count": len(costs),
            "job_cost_total": imported.reconciliation_summary["job_cost_total"],
        },
    )
    add_outbox(
        session,
        principal,
        PAYROLL_RECONCILED,
        "PayrollResultImport",
        imported.id,
        correlation_id,
        f"payroll-reconciled:{imported.id}",
        {
            "payroll_result_import_id": str(imported.id),
            "payroll_period_id": str(period.id),
            "job_cost_count": len(costs),
        },
    )
    await session.commit()
    return imported


def _compare_line(
    principal: Principal,
    import_id: uuid.UUID,
    expected: PayrollExportLine,
    actual: PayrollResultLine,
    expected_pay_date: date,
) -> list[PayrollReconciliationException]:
    exceptions = []
    checks = [
        ("PROVIDER_EMPLOYEE_MISMATCH", "provider employee", expected.provider_employee_id, actual.provider_employee_id),
        ("WORK_DATE_MISMATCH", "work date", expected.work_date, actual.work_date),
        ("PAY_DATE_MISMATCH", "pay date", expected_pay_date, actual.pay_date),
        ("GROSS_WAGE_MISMATCH", "gross wages", expected.gross_labor, actual.gross_wages),
    ]
    checks.extend(
        (f"{field.upper()}_MISMATCH", field.replace("_", " "), getattr(expected, field), getattr(actual, field))
        for field in (*HOUR_FIELDS, *RATE_FIELDS)
    )
    for code, label, expected_value, actual_value in checks:
        if expected_value != actual_value:
            exceptions.append(
                _exception(
                    principal,
                    import_id,
                    actual.id,
                    code,
                    f"Provider {label} does not match the immutable export snapshot",
                    str(expected_value),
                    str(actual_value),
                )
            )
    return exceptions


def _exception(
    principal: Principal,
    import_id: uuid.UUID,
    result_line_id: uuid.UUID | None,
    code: str,
    message: str,
    expected: str | None,
    actual: str | None,
) -> PayrollReconciliationException:
    return PayrollReconciliationException(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        payroll_result_import_id=import_id,
        payroll_result_line_id=result_line_id,
        code=code,
        message=message,
        expected_value=expected,
        actual_value=actual,
    )


def _source_checksum(data: PayrollResultImportCreate) -> str:
    payload = json.dumps(
        data.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _summary(
    data: PayrollResultImportCreate,
    exceptions: list[PayrollReconciliationException],
) -> dict[str, str | int]:
    return {
        "line_count": len(data.lines),
        "exception_count": len(exceptions),
        "gross_wages": str(sum((line.gross_wages for line in data.lines), ZERO)),
        "net_pay": str(sum((line.net_pay for line in data.lines), ZERO)),
    }


async def _period(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> PayrollPeriod:
    statement = select(PayrollPeriod).where(
        PayrollPeriod.tenant_id == principal.tenant_id,
        PayrollPeriod.id == period_id,
    )
    if for_update:
        statement = statement.with_for_update()
    period = await session.scalar(statement)
    if period is None:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    return period


async def _result_import(
    session: AsyncSession,
    principal: Principal,
    import_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> PayrollResultImport:
    statement = select(PayrollResultImport).where(
        PayrollResultImport.tenant_id == principal.tenant_id,
        PayrollResultImport.id == import_id,
    )
    if for_update:
        statement = statement.with_for_update()
    imported = await session.scalar(statement)
    if imported is None:
        raise HTTPException(status_code=404, detail="Payroll result import not found")
    return imported
