import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.documents.models import Document
from app.modules.federal_labor import repository
from app.modules.federal_labor.events import (
    EMPLOYEE_QUALIFICATION_CHANGED,
    FEDERAL_CHARGE_CODE_CLOSED,
    FEDERAL_INVOICE_SUPPORT_GENERATED,
)
from app.modules.federal_labor.models import (
    EmployeeQualification,
    FederalChargeCode,
    FederalChargeCodeStatus,
    FederalInvoiceSupport,
    FederalInvoiceSupportLine,
    FederalLaborRate,
)
from app.modules.federal_labor.permissions import (
    FEDERAL_CHARGE_CODES_MANAGE,
    FEDERAL_CHARGE_CODES_READ,
    FEDERAL_FLOOR_CHECK_READ,
    FEDERAL_INVOICE_SUPPORT_GENERATE,
    FEDERAL_INVOICE_SUPPORT_READ,
    FEDERAL_QUALIFICATIONS_MANAGE,
    FEDERAL_RATES_MANAGE,
)
from app.modules.federal_labor.preparation import prepare_invoice
from app.modules.federal_labor.schemas import (
    EmployeeQualificationCreate,
    FederalChargeCodeClose,
    FederalChargeCodeCreate,
    FederalInvoicePreview,
    FederalInvoiceSupportLineRead,
    FederalInvoiceSupportRead,
    FederalInvoiceSupportRequest,
    FederalLaborRateCreate,
    FloorCheckEntry,
    FloorCheckReport,
)
from app.modules.people.models import Employee
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.projects.models import Project


async def create_charge_code(
    session: AsyncSession,
    principal: Principal,
    data: FederalChargeCodeCreate,
) -> FederalChargeCode:
    principal.require(FEDERAL_CHARGE_CODES_MANAGE)
    await _advisory_lock(session, f"federal-charge-code:{principal.tenant_id}:{data.code}")
    if await repository.get_charge_code_by_code(
        session, principal.tenant_id, data.code
    ):
        raise HTTPException(status_code=409, detail="Federal charge code already exists")
    if data.project_id is not None and not await _record_exists(
        session, Project, principal.tenant_id, data.project_id
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    charge_code = FederalChargeCode(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        **data.model_dump(),
    )
    session.add(charge_code)
    await session.flush()
    add_audit(
        session,
        principal,
        "FederalChargeCode",
        charge_code.id,
        "created",
        correlation_uuid(),
        None,
        _state(charge_code),
    )
    await session.commit()
    return charge_code


async def list_charge_codes(
    session: AsyncSession,
    principal: Principal,
) -> list[FederalChargeCode]:
    principal.require(FEDERAL_CHARGE_CODES_READ)
    return await repository.list_charge_codes(session, principal.tenant_id)


async def close_charge_code(
    session: AsyncSession,
    principal: Principal,
    charge_code_id: uuid.UUID,
    expected_version: int,
    data: FederalChargeCodeClose,
) -> FederalChargeCode:
    principal.require(FEDERAL_CHARGE_CODES_MANAGE)
    charge_code = await repository.get_charge_code(
        session,
        principal.tenant_id,
        charge_code_id,
        for_update=True,
    )
    if charge_code is None:
        raise HTTPException(status_code=404, detail="Federal charge code not found")
    if charge_code.version != expected_version:
        raise HTTPException(status_code=409, detail="Federal charge code version conflict")
    if charge_code.status is FederalChargeCodeStatus.CLOSED:
        raise HTTPException(status_code=409, detail="Federal charge code is already closed")
    before = _state(charge_code)
    charge_code.status = FederalChargeCodeStatus.CLOSED
    charge_code.closed_at = datetime.now(UTC)
    charge_code.closed_by = principal.user_id
    charge_code.closed_reason = data.reason
    charge_code.updated_by = principal.user_id
    charge_code.version += 1
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "FederalChargeCode",
        charge_code.id,
        "closed",
        correlation_id,
        before,
        _state(charge_code),
        data.reason,
    )
    add_outbox(
        session,
        principal,
        FEDERAL_CHARGE_CODE_CLOSED,
        "FederalChargeCode",
        charge_code.id,
        correlation_id,
        f"federal-charge-code-closed:{charge_code.id}:{charge_code.version}",
        {
            "federal_charge_code_id": str(charge_code.id),
            "contract_code": charge_code.contract_code,
            "closed_reason": data.reason,
        },
    )
    await session.commit()
    return charge_code


async def create_rate(
    session: AsyncSession,
    principal: Principal,
    data: FederalLaborRateCreate,
) -> FederalLaborRate:
    principal.require(FEDERAL_RATES_MANAGE)
    charge_code = await repository.get_charge_code(
        session, principal.tenant_id, data.federal_charge_code_id
    )
    if charge_code is None:
        raise HTTPException(status_code=404, detail="Federal charge code not found")
    lock_key = (
        f"federal-rate:{principal.tenant_id}:{data.federal_charge_code_id}:"
        f"{data.labor_category}"
    )
    await _advisory_lock(session, lock_key)
    if await repository.overlapping_rate(
        session,
        principal.tenant_id,
        data.federal_charge_code_id,
        data.labor_category,
        data.effective_from,
        data.effective_to,
    ):
        raise HTTPException(
            status_code=409,
            detail="An overlapping federal labor rate already exists",
        )
    rate = FederalLaborRate(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        **data.model_dump(exclude={"currency"}),
        currency=data.currency.upper(),
    )
    session.add(rate)
    await session.flush()
    add_audit(
        session,
        principal,
        "FederalLaborRate",
        rate.id,
        "created",
        correlation_uuid(),
        None,
        _state(rate),
        data.source_reference,
    )
    await session.commit()
    return rate


async def list_rates(
    session: AsyncSession,
    principal: Principal,
    charge_code_id: uuid.UUID | None,
) -> list[FederalLaborRate]:
    principal.require(FEDERAL_INVOICE_SUPPORT_READ)
    return await repository.list_rates(
        session,
        principal.tenant_id,
        charge_code_id,
    )


async def create_qualification(
    session: AsyncSession,
    principal: Principal,
    data: EmployeeQualificationCreate,
) -> EmployeeQualification:
    principal.require(FEDERAL_QUALIFICATIONS_MANAGE)
    if not await _record_exists(
        session, Employee, principal.tenant_id, data.employee_id
    ):
        raise HTTPException(status_code=404, detail="Employee not found")
    if data.evidence_document_id is not None and not await _record_exists(
        session,
        Document,
        principal.tenant_id,
        data.evidence_document_id,
    ):
        raise HTTPException(status_code=404, detail="Evidence document not found")
    lock_key = (
        f"employee-qualification:{principal.tenant_id}:{data.employee_id}:"
        f"{data.qualification_code}"
    )
    await _advisory_lock(session, lock_key)
    if await repository.overlapping_qualification(
        session,
        principal.tenant_id,
        data.employee_id,
        data.qualification_code,
        data.effective_from,
        data.effective_to,
    ):
        raise HTTPException(
            status_code=409,
            detail="An overlapping employee qualification already exists",
        )
    qualification = EmployeeQualification(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        verified_at=datetime.now(UTC),
        verified_by=principal.user_id,
        **data.model_dump(),
    )
    session.add(qualification)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "EmployeeQualification",
        qualification.id,
        "recorded",
        correlation_id,
        None,
        _state(qualification),
    )
    add_outbox(
        session,
        principal,
        EMPLOYEE_QUALIFICATION_CHANGED,
        "EmployeeQualification",
        qualification.id,
        correlation_id,
        f"employee-qualification-recorded:{qualification.id}",
        {
            "employee_qualification_id": str(qualification.id),
            "employee_id": str(qualification.employee_id),
            "qualification_code": qualification.qualification_code,
        },
    )
    await session.commit()
    return qualification


async def list_qualifications(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID | None,
) -> list[EmployeeQualification]:
    principal.require(FEDERAL_INVOICE_SUPPORT_READ)
    return await repository.list_qualifications(
        session,
        principal.tenant_id,
        employee_id,
    )


async def floor_check(
    session: AsyncSession,
    principal: Principal,
    period_start: Any,
    period_end: Any,
    contract_code: str | None,
) -> FloorCheckReport:
    principal.require(FEDERAL_FLOOR_CHECK_READ)
    if period_end < period_start:
        raise HTTPException(status_code=422, detail="Period end precedes period start")
    rows = await repository.floor_check_time(
        session,
        principal.tenant_id,
        period_start,
        period_end,
        contract_code,
    )
    entries: dict[uuid.UUID, FloorCheckEntry] = {}
    for time_entry, employee, charge_code, payroll_line, invoice_line in rows:
        existing = entries.get(time_entry.id)
        payroll_status = "PAID" if payroll_line is not None else "NOT_PAID"
        invoice_status = "INVOICED" if invoice_line is not None else "NOT_INVOICED"
        if existing is not None:
            entries[time_entry.id] = existing.model_copy(
                update={
                    "payroll_status": (
                        "PAID"
                        if existing.payroll_status == "PAID" or payroll_line is not None
                        else "NOT_PAID"
                    ),
                    "invoice_status": (
                        "INVOICED"
                        if existing.invoice_status == "INVOICED" or invoice_line is not None
                        else "NOT_INVOICED"
                    ),
                }
            )
            continue
        entries[time_entry.id] = FloorCheckEntry(
            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            work_date=time_entry.work_date,
            location=time_entry.location,
            description=time_entry.description,
            contract_code=charge_code.contract_code,
            task_order=charge_code.task_order,
            clin=charge_code.clin,
            labor_category=(
                time_entry.labor_category or charge_code.labor_category or "UNCLASSIFIED"
            ),
            approved_hours=time_entry.total_hours,
            time_entry_status=time_entry.status.value,
            certified_at=time_entry.certified_at,
            approved_at=time_entry.approved_at,
            approved_by=time_entry.approved_by,
            payroll_status=payroll_status,
            invoice_status=invoice_status,
        )
    return FloorCheckReport(
        period_start=period_start,
        period_end=period_end,
        entries=list(entries.values()),
    )


async def preview_invoice_support(
    session: AsyncSession,
    principal: Principal,
    data: FederalInvoiceSupportRequest,
) -> FederalInvoicePreview:
    principal.require(FEDERAL_INVOICE_SUPPORT_READ)
    return await prepare_invoice(session, principal, data)


async def generate_invoice_support(
    session: AsyncSession,
    principal: Principal,
    data: FederalInvoiceSupportRequest,
) -> FederalInvoiceSupportRead:
    principal.require(FEDERAL_INVOICE_SUPPORT_GENERATE)
    lock_key = (
        f"federal-invoice:{principal.tenant_id}:{data.contract_code}:"
        f"{data.task_order or '-'}:{data.invoice_period_start}:{data.invoice_period_end}"
    )
    await _advisory_lock(session, lock_key)
    preview = await prepare_invoice(session, principal, data)
    if not preview.ready:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Federal invoice support has blocking exceptions",
                "exceptions": [
                    item.model_dump(mode="json") for item in preview.exceptions
                ],
            },
        )
    snapshot = {
        "request": data.model_dump(mode="json"),
        "calculation": {
            "approved_hours": (
                "regular_hours + overtime_hours + double_time_hours"
            ),
            "extended_amount": (
                "regular_hours * regular_bill_rate + overtime_hours * "
                "overtime_bill_rate + double_time_hours * double_time_bill_rate"
            ),
            "rounding": "Each line is rounded half-up to USD cents",
        },
        "preview": preview.model_dump(mode="json"),
    }
    checksum = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    latest = await repository.latest_support(
        session,
        principal.tenant_id,
        data.contract_code,
        data.task_order,
        data.invoice_period_start,
        data.invoice_period_end,
    )
    if latest is not None and latest.content_checksum == checksum:
        raise HTTPException(
            status_code=409,
            detail="Identical immutable federal invoice support already exists",
        )
    support = FederalInvoiceSupport(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        contract_code=data.contract_code,
        task_order=data.task_order,
        invoice_number=data.invoice_number,
        invoice_period_start=data.invoice_period_start,
        invoice_period_end=data.invoice_period_end,
        artifact_version=(latest.artifact_version + 1 if latest else 1),
        generated_at=datetime.now(UTC),
        generated_by=principal.user_id,
        total_approved_hours=preview.total_approved_hours,
        total_extended_amount=preview.total_extended_amount,
        source_snapshot=snapshot,
        content_checksum=checksum,
    )
    session.add(support)
    await session.flush()
    for line in preview.lines:
        session.add(_support_line(principal, support.id, line.model_dump()))
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "FederalInvoiceSupport",
        support.id,
        "generated",
        correlation_id,
        None,
        _state(support),
    )
    add_outbox(
        session,
        principal,
        FEDERAL_INVOICE_SUPPORT_GENERATED,
        "FederalInvoiceSupport",
        support.id,
        correlation_id,
        f"federal-invoice-support-generated:{support.id}",
        {
            "federal_invoice_support_id": str(support.id),
            "contract_code": support.contract_code,
            "task_order": support.task_order,
            "artifact_version": support.artifact_version,
            "content_checksum": support.content_checksum,
        },
    )
    await session.flush()
    result = await _support_read(session, principal.tenant_id, support)
    await session.commit()
    return result


async def list_invoice_support(
    session: AsyncSession,
    principal: Principal,
) -> list[FederalInvoiceSupportRead]:
    principal.require(FEDERAL_INVOICE_SUPPORT_READ)
    supports = await repository.list_supports(session, principal.tenant_id)
    return [FederalInvoiceSupportRead.model_validate(support) for support in supports]


async def get_invoice_support(
    session: AsyncSession,
    principal: Principal,
    support_id: uuid.UUID,
) -> FederalInvoiceSupportRead:
    principal.require(FEDERAL_INVOICE_SUPPORT_READ)
    support = await repository.get_support(
        session,
        principal.tenant_id,
        support_id,
    )
    if support is None:
        raise HTTPException(status_code=404, detail="Federal invoice support not found")
    return await _support_read(session, principal.tenant_id, support)


async def _support_read(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    support: FederalInvoiceSupport,
) -> FederalInvoiceSupportRead:
    result = FederalInvoiceSupportRead.model_validate(support)
    lines = await repository.support_lines(session, tenant_id, support.id)
    return result.model_copy(
        update={
            "lines": [
                FederalInvoiceSupportLineRead.model_validate(line) for line in lines
            ]
        }
    )


def _support_line(
    principal: Principal,
    support_id: uuid.UUID,
    data: dict[str, Any],
) -> FederalInvoiceSupportLine:
    return FederalInvoiceSupportLine(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        federal_invoice_support_id=support_id,
        **data,
    )


async def _record_exists(
    session: AsyncSession,
    model: type[Any],
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
) -> bool:
    return (
        await session.scalar(
            select(model.id).where(
                model.tenant_id == tenant_id,
                model.id == record_id,
            )
        )
        is not None
    )


async def _advisory_lock(session: AsyncSession, key: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": key},
    )


def _state(record: Any) -> dict[str, Any]:
    return jsonable_encoder(
        {
            column.name: getattr(record, column.name)
            for column in record.__table__.columns
        }
    )
