import hashlib
import uuid
from asyncio import to_thread
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.core.storage import get_object_storage
from app.modules.payroll import repository
from app.modules.payroll.adapters import provider_adapter
from app.modules.payroll.events import PAYROLL_EXPORT_GENERATED, PAYROLL_PERIOD_LOCKED
from app.modules.payroll.models import (
    EmployeePayRate,
    PayrollExport,
    PayrollExportLine,
    PayrollMappingType,
    PayrollPeriod,
    PayrollPeriodExportStatus,
    PayrollPeriodStatus,
    PayrollProviderMapping,
)
from app.modules.payroll.permissions import (
    PAYROLL_EXPORT,
    PAYROLL_MAPPINGS_MANAGE,
    PAYROLL_PERIODS_MANAGE,
    PAYROLL_REVIEW,
    PAYROLL_VIEW_WAGES,
)
from app.modules.payroll.schemas import (
    EmployeePayRateCreate,
    PayrollExportCreate,
    PayrollMappingCreate,
    PayrollPeriodCreate,
    PayrollPeriodTransition,
    PayrollPreview,
    PayrollPreviewEmployee,
    PayrollPreviewException,
)
from app.modules.people.models import Employee
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.timekeeping.models import TimeEntry, TimeEntryStatus

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
PERIOD_TRANSITIONS = {
    PayrollPeriodStatus.OPEN: PayrollPeriodStatus.EMPLOYEE_REVIEW,
    PayrollPeriodStatus.EMPLOYEE_REVIEW: PayrollPeriodStatus.SUPERVISOR_REVIEW,
    PayrollPeriodStatus.SUPERVISOR_REVIEW: PayrollPeriodStatus.PAYROLL_REVIEW,
    PayrollPeriodStatus.PAYROLL_REVIEW: PayrollPeriodStatus.LOCKED,
}
EARNING_FIELDS = {
    "REGULAR": "regular_hours",
    "OVERTIME": "overtime_hours",
    "DOUBLE_TIME": "double_time_hours",
    "TRAVEL": "travel_hours",
    "LEAVE": "leave_hours",
    "INDIRECT": "indirect_hours",
}


@dataclass(frozen=True)
class PreparedLine:
    entry: TimeEntry
    employee: Employee
    rate: EmployeePayRate | None
    mappings: dict[str, str]
    mapping_versions: dict[str, dict[str, str | int | None]]
    gross_labor: Decimal | None
    job_cost_amount: Decimal | None


async def create_period(
    session: AsyncSession,
    principal: Principal,
    data: PayrollPeriodCreate,
) -> PayrollPeriod:
    principal.require(PAYROLL_PERIODS_MANAGE)
    provider = _provider_name(data.provider)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"payroll-period:{principal.tenant_id}"},
    )
    if await repository.find_overlapping_period(
        session,
        principal.tenant_id,
        data.period_start,
        data.period_end,
    ):
        raise HTTPException(status_code=409, detail="Payroll period overlaps an existing period")
    period = PayrollPeriod(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        provider=provider,
        **data.model_dump(exclude={"provider"}),
    )
    session.add(period)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "PayrollPeriod",
        period.id,
        "created",
        correlation_id,
        None,
        _period_state(period),
    )
    await session.commit()
    return period


async def list_periods(
    session: AsyncSession,
    principal: Principal,
) -> list[PayrollPeriod]:
    principal.require(PAYROLL_REVIEW)
    return await repository.list_periods(session, principal.tenant_id)


async def list_pay_rates(
    session: AsyncSession,
    principal: Principal,
) -> list[EmployeePayRate]:
    principal.require(PAYROLL_MAPPINGS_MANAGE)
    principal.require(PAYROLL_VIEW_WAGES)
    return await repository.list_pay_rates(session, principal.tenant_id)


async def list_mappings(
    session: AsyncSession,
    principal: Principal,
    provider: str | None,
) -> list[PayrollProviderMapping]:
    principal.require(PAYROLL_MAPPINGS_MANAGE)
    normalized = _provider_name(provider) if provider else None
    return await repository.list_mappings(session, principal.tenant_id, normalized)


async def list_exports(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
) -> list[PayrollExport]:
    principal.require(PAYROLL_EXPORT)
    await _period(session, principal, period_id)
    exports = await repository.list_exports(session, principal.tenant_id, period_id)
    if PAYROLL_VIEW_WAGES in principal.permissions:
        return exports
    return [item for item in exports if not item.includes_sensitive_fields]


async def add_pay_rate(
    session: AsyncSession,
    principal: Principal,
    data: EmployeePayRateCreate,
) -> EmployeePayRate:
    principal.require(PAYROLL_MAPPINGS_MANAGE)
    principal.require(PAYROLL_VIEW_WAGES)
    await _employee_exists(session, principal.tenant_id, data.employee_id)
    conflict = await session.scalar(
        select(EmployeePayRate.id).where(
            EmployeePayRate.tenant_id == principal.tenant_id,
            EmployeePayRate.employee_id == data.employee_id,
            EmployeePayRate.effective_from <= (data.effective_to or date.max),
            (EmployeePayRate.effective_to.is_(None))
            | (EmployeePayRate.effective_to >= data.effective_from),
        )
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="Pay-rate effective dates overlap")
    rate = EmployeePayRate(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        **data.model_dump(),
    )
    session.add(rate)
    await session.flush()
    add_audit(
        session,
        principal,
        "EmployeePayRate",
        rate.id,
        "created",
        correlation_uuid(),
        None,
        _rate_state(rate),
    )
    await session.commit()
    return rate


async def add_mapping(
    session: AsyncSession,
    principal: Principal,
    data: PayrollMappingCreate,
) -> PayrollProviderMapping:
    principal.require(PAYROLL_MAPPINGS_MANAGE)
    provider = _provider_name(data.provider)
    conflict = await session.scalar(
        select(PayrollProviderMapping.id).where(
            PayrollProviderMapping.tenant_id == principal.tenant_id,
            PayrollProviderMapping.provider == provider,
            PayrollProviderMapping.mapping_type == data.mapping_type,
            PayrollProviderMapping.internal_key == data.internal_key,
            PayrollProviderMapping.effective_from <= (data.effective_to or date.max),
            (PayrollProviderMapping.effective_to.is_(None))
            | (PayrollProviderMapping.effective_to >= data.effective_from),
        )
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="Provider mapping effective dates overlap")
    mapping = PayrollProviderMapping(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        provider=provider,
        **data.model_dump(exclude={"provider"}),
    )
    session.add(mapping)
    await session.flush()
    add_audit(
        session,
        principal,
        "PayrollProviderMapping",
        mapping.id,
        "created",
        correlation_uuid(),
        None,
        _mapping_state(mapping),
    )
    await session.commit()
    return mapping


async def preview_period(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
) -> PayrollPreview:
    principal.require(PAYROLL_REVIEW)
    period = await _period(session, principal, period_id)
    lines, exceptions, unapproved = await _prepare_period(session, principal, period)
    return _preview(
        period,
        lines,
        exceptions,
        unapproved,
        PAYROLL_VIEW_WAGES in principal.permissions,
    )


async def transition_period(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
    expected_version: int,
    data: PayrollPeriodTransition,
) -> PayrollPeriod:
    principal.require(PAYROLL_PERIODS_MANAGE)
    period = await _period(session, principal, period_id, for_update=True)
    if period.version != expected_version:
        raise HTTPException(status_code=409, detail="Payroll period version conflict")
    expected_target = PERIOD_TRANSITIONS.get(period.status)
    if expected_target is None or data.target_status is not expected_target:
        raise HTTPException(status_code=409, detail="Invalid payroll period transition")
    if data.target_status in {
        PayrollPeriodStatus.PAYROLL_REVIEW,
        PayrollPeriodStatus.LOCKED,
    }:
        principal.require(PAYROLL_REVIEW)
    before = _period_state(period)
    event_type = None
    if data.target_status is PayrollPeriodStatus.LOCKED:
        lines, exceptions, unapproved = await _prepare_period(session, principal, period)
        preview = _preview(period, lines, exceptions, unapproved, True)
        if not preview.ready_to_lock:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Payroll period has blocking exceptions",
                    "exceptions": [item.model_dump(mode="json") for item in preview.exceptions],
                },
            )
        period.locked_at = datetime.now(UTC)
        period.approved_by = principal.user_id
        period.validation_snapshot = preview.model_dump(mode="json")
        event_type = PAYROLL_PERIOD_LOCKED
    period.status = data.target_status
    period.review_reason = data.reason
    period.updated_by = principal.user_id
    period.version += 1
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "PayrollPeriod",
        period.id,
        "locked" if event_type else "review_advanced",
        correlation_id,
        before,
        _period_state(period),
        data.reason,
    )
    if event_type:
        add_outbox(
            session,
            principal,
            event_type,
            "PayrollPeriod",
            period.id,
            correlation_id,
            f"payroll-period-locked:{period.id}:{period.version}",
            {"payroll_period_id": str(period.id)},
        )
    await session.commit()
    return period


async def generate_export(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
    expected_version: int,
    data: PayrollExportCreate,
) -> PayrollExport:
    principal.require(PAYROLL_EXPORT)
    if data.include_sensitive_fields:
        principal.require(PAYROLL_VIEW_WAGES)
    period = await _period(session, principal, period_id, for_update=True)
    if period.version != expected_version:
        raise HTTPException(status_code=409, detail="Payroll period version conflict")
    if period.status not in {PayrollPeriodStatus.LOCKED, PayrollPeriodStatus.EXPORTED}:
        raise HTTPException(status_code=409, detail="Payroll period must be locked")
    if await repository.find_export(
        session,
        principal.tenant_id,
        period.id,
        period.provider,
        data.format,
    ):
        raise HTTPException(status_code=409, detail="Duplicate payroll export detected")
    lines, exceptions, unapproved = await _prepare_period(session, principal, period)
    preview = _preview(period, lines, exceptions, unapproved, True)
    if not preview.ready_to_lock:
        raise HTTPException(status_code=409, detail="Payroll period is no longer exportable")
    rows = [_export_row(line, data.include_sensitive_fields, period) for line in lines]
    content, content_type, extension = provider_adapter(period.provider).build_export(
        rows,
        data.format,
    )
    checksum = hashlib.sha256(content).hexdigest()
    export_id = uuid.uuid4()
    filename = (
        f"payroll-{period.period_start}-{period.period_end}-"
        f"{period.provider.lower()}-v1.{extension}"
    )
    storage_key = (
        f"tenants/{principal.tenant_id}/payroll/{period.id}/"
        f"exports/{export_id}/{checksum}.{extension}"
    )
    await to_thread(
        get_object_storage().put_immutable,
        storage_key,
        content,
        content_type,
    )
    generated_at = datetime.now(UTC)
    payroll_export = PayrollExport(
        id=export_id,
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        payroll_period_id=period.id,
        provider=period.provider,
        format=data.format,
        artifact_version=1,
        generated_at=generated_at,
        generated_by=principal.user_id,
        file_checksum=checksum,
        storage_key=storage_key,
        filename=filename,
        content_type=content_type,
        includes_sensitive_fields=data.include_sensitive_fields,
        totals_snapshot=(
            preview.model_dump(mode="json")
            if data.include_sensitive_fields
            else redact_wages(preview.model_dump(mode="json"))
        ),
    )
    session.add(payroll_export)
    await session.flush()
    for line in lines:
        session.add(
            _export_line(
                principal,
                payroll_export.id,
                line,
                data.include_sensitive_fields,
            )
        )
    before = _period_state(period)
    period.status = PayrollPeriodStatus.EXPORTED
    period.export_status = PayrollPeriodExportStatus.GENERATED
    period.updated_by = principal.user_id
    period.version += 1
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "PayrollExport",
        payroll_export.id,
        "generated",
        correlation_id,
        None,
        _export_state(payroll_export),
    )
    add_audit(
        session,
        principal,
        "PayrollPeriod",
        period.id,
        "export_generated",
        correlation_id,
        before,
        _period_state(period),
    )
    add_outbox(
        session,
        principal,
        PAYROLL_EXPORT_GENERATED,
        "PayrollExport",
        payroll_export.id,
        correlation_id,
        f"payroll-export-generated:{payroll_export.id}",
        {
            "payroll_export_id": str(payroll_export.id),
            "payroll_period_id": str(period.id),
            "checksum": checksum,
        },
    )
    await session.commit()
    return payroll_export


async def download_export(
    session: AsyncSession,
    principal: Principal,
    export_id: uuid.UUID,
) -> tuple[PayrollExport, bytes]:
    principal.require(PAYROLL_EXPORT)
    payroll_export = await repository.get_export(
        session,
        principal.tenant_id,
        export_id,
    )
    if payroll_export is None:
        raise HTTPException(status_code=404, detail="Payroll export not found")
    if payroll_export.includes_sensitive_fields:
        principal.require(PAYROLL_VIEW_WAGES)
    content = await to_thread(get_object_storage().get, payroll_export.storage_key)
    if hashlib.sha256(content).hexdigest() != payroll_export.file_checksum:
        raise HTTPException(status_code=409, detail="Payroll export integrity check failed")
    return payroll_export, content


async def _prepare_period(
    session: AsyncSession,
    principal: Principal,
    period: PayrollPeriod,
) -> tuple[list[PreparedLine], list[PayrollPreviewException], int]:
    records = await repository.period_time(session, principal.tenant_id, period)
    mappings = await repository.period_mappings(
        session,
        principal.tenant_id,
        period.provider,
        period.period_start,
        period.period_end,
    )
    rates = await repository.period_pay_rates(
        session,
        principal.tenant_id,
        period.period_start,
        period.period_end,
    )
    mapping_index = _mapping_index(mappings)
    rate_index = _rate_index(rates)
    lines: list[PreparedLine] = []
    exceptions: list[PayrollPreviewException] = []
    unapproved = 0
    for entry, employee in records:
        if entry.status is not TimeEntryStatus.APPROVED:
            unapproved += 1
            exceptions.append(
                PayrollPreviewException(
                    code="UNAPPROVED_TIME",
                    message=f"{employee.employee_number} has unapproved time on {entry.work_date}",
                    time_entry_id=entry.id,
                    employee_id=employee.id,
                )
            )
            continue
        line, line_exceptions = _prepare_line(
            entry,
            employee,
            mapping_index,
            rate_index,
        )
        lines.append(line)
        exceptions.extend(line_exceptions)
    if not lines:
        exceptions.append(
            PayrollPreviewException(
                code="NO_APPROVED_TIME",
                message="Payroll period has no approved time to export",
            )
        )
    return lines, exceptions, unapproved


def _prepare_line(
    entry: TimeEntry,
    employee: Employee,
    mapping_index: dict[tuple[PayrollMappingType, str], list[PayrollProviderMapping]],
    rate_index: dict[uuid.UUID, list[EmployeePayRate]],
) -> tuple[PreparedLine, list[PayrollPreviewException]]:
    exceptions: list[PayrollPreviewException] = []
    resolved: dict[str, str] = {}
    mapping_versions: dict[str, dict[str, str | int | None]] = {}

    def require_mapping(mapping_type: PayrollMappingType, key: str, label: str) -> None:
        mapping = _dated(mapping_index.get((mapping_type, key), []), entry.work_date)
        if mapping is None:
            exceptions.append(
                PayrollPreviewException(
                    code=f"MISSING_{mapping_type.value}_MAPPING",
                    message=f"Missing {label} mapping for {key}",
                    time_entry_id=entry.id,
                    employee_id=employee.id,
                    internal_key=key,
                )
            )
        else:
            snapshot_key = f"{mapping_type.value}:{key}"
            resolved[snapshot_key] = mapping.external_code
            mapping_versions[snapshot_key] = {
                "mapping_id": str(mapping.id),
                "version": mapping.version,
                "external_code": mapping.external_code,
                "effective_from": mapping.effective_from.isoformat(),
                "effective_to": (
                    mapping.effective_to.isoformat() if mapping.effective_to else None
                ),
            }

    require_mapping(PayrollMappingType.EMPLOYEE, str(employee.id), "employee")
    for earning, field in EARNING_FIELDS.items():
        if getattr(entry, field) > 0:
            require_mapping(PayrollMappingType.EARNING, earning, "earning code")
    if entry.project_id is not None:
        require_mapping(PayrollMappingType.PROJECT, str(entry.project_id), "project")
    if entry.cost_code:
        require_mapping(PayrollMappingType.COST_CODE, entry.cost_code, "cost code")
    if entry.labor_category:
        require_mapping(
            PayrollMappingType.LABOR_CATEGORY,
            entry.labor_category,
            "labor category",
        )
    rate = _dated(rate_index.get(employee.id, []), entry.work_date)
    if rate is None:
        exceptions.append(
            PayrollPreviewException(
                code="MISSING_PAY_RATE",
                message=f"Missing effective pay rate for {employee.employee_number}",
                time_entry_id=entry.id,
                employee_id=employee.id,
            )
        )
    if entry.wage_determination and not entry.work_classification:
        exceptions.append(
            PayrollPreviewException(
                code="MISSING_WAGE_CLASSIFICATION",
                message="Wage-determination time requires a work classification",
                time_entry_id=entry.id,
                employee_id=employee.id,
            )
        )
    gross, job_cost = _labor_cost(entry, rate)
    return (
        PreparedLine(
            entry,
            employee,
            rate,
            resolved,
            mapping_versions,
            gross,
            job_cost,
        ),
        exceptions,
    )


def _preview(
    period: PayrollPeriod,
    lines: list[PreparedLine],
    exceptions: list[PayrollPreviewException],
    unapproved: int,
    reveal_wages: bool,
) -> PayrollPreview:
    grouped: dict[uuid.UUID, list[PreparedLine]] = defaultdict(list)
    for line in lines:
        grouped[line.employee.id].append(line)
    employees = []
    for employee_lines in grouped.values():
        first = employee_lines[0]
        employees.append(
            PayrollPreviewEmployee(
                employee_id=first.employee.id,
                employee_number=first.employee.employee_number,
                employee_name=f"{first.employee.first_name} {first.employee.last_name}",
                regular_hours=_sum(employee_lines, "regular_hours"),
                overtime_hours=_sum(employee_lines, "overtime_hours"),
                double_time_hours=_sum(employee_lines, "double_time_hours"),
                travel_hours=_sum(employee_lines, "travel_hours"),
                leave_hours=_sum(employee_lines, "leave_hours"),
                indirect_hours=_sum(employee_lines, "indirect_hours"),
                estimated_gross_labor=(
                    sum((line.gross_labor or ZERO for line in employee_lines), ZERO)
                    if reveal_wages
                    else None
                ),
                source_time_entry_ids=[line.entry.id for line in employee_lines],
            )
        )
    employees.sort(key=lambda item: item.employee_number)
    gross = sum((line.gross_labor or ZERO for line in lines), ZERO)
    return PayrollPreview(
        payroll_period_id=period.id,
        provider=period.provider,
        approved_entry_count=len(lines),
        unapproved_entry_count=unapproved,
        employees=employees,
        exceptions=exceptions,
        totals={
            "regular_hours": str(_sum(lines, "regular_hours")),
            "overtime_hours": str(_sum(lines, "overtime_hours")),
            "double_time_hours": str(_sum(lines, "double_time_hours")),
            "travel_hours": str(_sum(lines, "travel_hours")),
            "leave_hours": str(_sum(lines, "leave_hours")),
            "indirect_hours": str(_sum(lines, "indirect_hours")),
            "estimated_gross_labor": str(gross) if reveal_wages else None,
            "employee_count": len(employees),
        },
        calculation={
            "gross_labor": (
                "regular*base + overtime*overtime_rate + double_time*double_time_rate "
                "+ (travel+leave+indirect)*base"
            ),
            "job_cost": "gross_labor + total_hours*(fringe_rate+cash_in_lieu_rate)",
            "sources": "Approved, non-corrected TimeEntry records and date-effective rates/mappings",
        },
        ready_to_lock=not exceptions and bool(lines),
    )


def _export_row(
    line: PreparedLine,
    include_sensitive: bool,
    period: PayrollPeriod | None = None,
) -> dict:
    entry = line.entry
    employee = line.employee
    rate = line.rate
    project_code = line.mappings.get(f"PROJECT:{entry.project_id}")
    return {
        "employee_id": employee.employee_number,
        "employee_name": f"{employee.first_name} {employee.last_name}",
        "provider_employee_id": line.mappings.get(f"EMPLOYEE:{employee.id}", ""),
        "work_date": entry.work_date,
        "period_start": period.period_start if period else None,
        "period_end": period.period_end if period else None,
        "pay_date": period.pay_date if period else None,
        "regular_hours": entry.regular_hours,
        "regular_earning_code": line.mappings.get("EARNING:REGULAR"),
        "overtime_hours": entry.overtime_hours,
        "overtime_earning_code": line.mappings.get("EARNING:OVERTIME"),
        "double_time_hours": entry.double_time_hours,
        "double_time_earning_code": line.mappings.get("EARNING:DOUBLE_TIME"),
        "travel_hours": entry.travel_hours,
        "travel_earning_code": line.mappings.get("EARNING:TRAVEL"),
        "leave_hours": entry.leave_hours,
        "leave_earning_code": line.mappings.get("EARNING:LEAVE"),
        "indirect_hours": entry.indirect_hours,
        "indirect_earning_code": line.mappings.get("EARNING:INDIRECT"),
        "project_code": project_code,
        "cost_code": (
            line.mappings.get(f"COST_CODE:{entry.cost_code}") if entry.cost_code else None
        ),
        "charge_code": entry.charge_code,
        "labor_category": (
            line.mappings.get(f"LABOR_CATEGORY:{entry.labor_category}")
            if entry.labor_category
            else None
        ),
        "work_classification": entry.work_classification,
        "wage_determination": entry.wage_determination,
        "contract_code": entry.contract_code,
        "task_order": entry.task_order,
        "clin": entry.clin,
        "funding_line": entry.funding_line,
        "base_rate": rate.base_rate if include_sensitive and rate else None,
        "overtime_rate": rate.overtime_rate if include_sensitive and rate else None,
        "double_time_rate": rate.double_time_rate if include_sensitive and rate else None,
        "fringe_rate": rate.fringe_rate if include_sensitive and rate else None,
        "cash_in_lieu_rate": (
            rate.cash_in_lieu_rate if include_sensitive and rate else None
        ),
        "gross_labor": line.gross_labor if include_sensitive else None,
        "job_cost_amount": line.job_cost_amount if include_sensitive else None,
    }


def _export_line(
    principal: Principal,
    export_id: uuid.UUID,
    line: PreparedLine,
    include_sensitive: bool,
) -> PayrollExportLine:
    del include_sensitive
    # The downloadable artifact may omit wages, but the internal immutable
    # reconciliation snapshot must always retain authoritative rates and cost.
    row = _export_row(line, True)
    entry = line.entry
    employee = line.employee
    return PayrollExportLine(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        payroll_export_id=export_id,
        time_entry_id=entry.id,
        employee_id=employee.id,
        employee_number=employee.employee_number,
        employee_name=f"{employee.first_name} {employee.last_name}",
        provider_employee_id=row["provider_employee_id"],
        work_date=entry.work_date,
        regular_hours=entry.regular_hours,
        overtime_hours=entry.overtime_hours,
        double_time_hours=entry.double_time_hours,
        travel_hours=entry.travel_hours,
        leave_hours=entry.leave_hours,
        indirect_hours=entry.indirect_hours,
        project_id=entry.project_id,
        project_code=row["project_code"],
        cost_code=row["cost_code"],
        charge_code=entry.charge_code,
        contract_code=entry.contract_code,
        task_order=entry.task_order,
        clin=entry.clin,
        funding_line=entry.funding_line,
        labor_category=row["labor_category"],
        work_classification=entry.work_classification,
        wage_determination=entry.wage_determination,
        base_rate=row["base_rate"],
        overtime_rate=row["overtime_rate"],
        double_time_rate=row["double_time_rate"],
        fringe_rate=row["fringe_rate"],
        cash_in_lieu_rate=row["cash_in_lieu_rate"],
        gross_labor=row["gross_labor"],
        job_cost_amount=row["job_cost_amount"],
        mapping_snapshot={
            **line.mapping_versions,
            "PAY_RATE": (
                {
                    "pay_rate_id": str(line.rate.id),
                    "version": line.rate.version,
                    "effective_from": line.rate.effective_from.isoformat(),
                    "effective_to": (
                        line.rate.effective_to.isoformat()
                        if line.rate.effective_to
                        else None
                    ),
                }
                if line.rate
                else None
            ),
        },
    )


def _labor_cost(
    entry: TimeEntry,
    rate: EmployeePayRate | None,
) -> tuple[Decimal | None, Decimal | None]:
    if rate is None:
        return None, None
    gross = (
        entry.regular_hours * rate.base_rate
        + entry.overtime_hours * rate.overtime_rate
        + entry.double_time_hours * rate.double_time_rate
        + (entry.travel_hours + entry.leave_hours + entry.indirect_hours) * rate.base_rate
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    burden = (
        entry.total_hours * (rate.fringe_rate + rate.cash_in_lieu_rate)
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    return gross, gross + burden


def _mapping_index(
    mappings: list[PayrollProviderMapping],
) -> dict[tuple[PayrollMappingType, str], list[PayrollProviderMapping]]:
    result: dict[tuple[PayrollMappingType, str], list[PayrollProviderMapping]] = defaultdict(
        list
    )
    for mapping in mappings:
        result[(mapping.mapping_type, mapping.internal_key)].append(mapping)
    return result


def _rate_index(rates: list[EmployeePayRate]) -> dict[uuid.UUID, list[EmployeePayRate]]:
    result: dict[uuid.UUID, list[EmployeePayRate]] = defaultdict(list)
    for rate in rates:
        result[rate.employee_id].append(rate)
    return result


def _dated(records: list, effective_date: date):
    valid = [
        record
        for record in records
        if record.effective_from <= effective_date
        and (record.effective_to is None or record.effective_to >= effective_date)
    ]
    return max(valid, key=lambda item: item.effective_from) if valid else None


def _sum(lines: list[PreparedLine], field: str) -> Decimal:
    return sum((getattr(line.entry, field) for line in lines), ZERO)


async def _period(
    session: AsyncSession,
    principal: Principal,
    period_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> PayrollPeriod:
    period = await repository.get_period(
        session,
        principal.tenant_id,
        period_id,
        for_update=for_update,
    )
    if period is None:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    return period


async def _employee_exists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    if (
        await session.scalar(
            select(Employee.id).where(
                Employee.tenant_id == tenant_id,
                Employee.id == employee_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Employee not found")


def _provider_name(value: str) -> str:
    try:
        return provider_adapter(value).name
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _period_state(period: PayrollPeriod) -> dict[str, str]:
    return {
        "period_start": str(period.period_start),
        "period_end": str(period.period_end),
        "provider": period.provider,
        "status": period.status,
        "export_status": period.export_status,
        "version": str(period.version),
    }


def _rate_state(rate: EmployeePayRate) -> dict[str, str]:
    return {
        "employee_id": str(rate.employee_id),
        "effective_from": str(rate.effective_from),
        "effective_to": str(rate.effective_to),
        "base_rate": "[REDACTED]",
        "overtime_rate": "[REDACTED]",
        "double_time_rate": "[REDACTED]",
        "fringe_rate": "[REDACTED]",
        "cash_in_lieu_rate": "[REDACTED]",
    }


def _mapping_state(mapping: PayrollProviderMapping) -> dict[str, str]:
    return {
        "provider": mapping.provider,
        "mapping_type": mapping.mapping_type,
        "internal_key": mapping.internal_key,
        "external_code": mapping.external_code,
        "effective_from": str(mapping.effective_from),
        "effective_to": str(mapping.effective_to),
    }


def _export_state(payroll_export: PayrollExport) -> dict[str, str]:
    return {
        "payroll_period_id": str(payroll_export.payroll_period_id),
        "provider": payroll_export.provider,
        "format": payroll_export.format,
        "artifact_version": str(payroll_export.artifact_version),
        "file_checksum": payroll_export.file_checksum,
        "status": payroll_export.status,
    }


def redact_wages(snapshot: dict | None) -> dict | None:
    if snapshot is None:
        return None
    redacted = deepcopy(snapshot)
    totals = redacted.get("totals")
    if isinstance(totals, dict):
        totals["estimated_gross_labor"] = None
    employees = redacted.get("employees")
    if isinstance(employees, list):
        for employee in employees:
            if isinstance(employee, dict):
                employee["estimated_gross_labor"] = None
    return redacted
