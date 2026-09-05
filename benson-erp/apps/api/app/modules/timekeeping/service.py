import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.federal_labor.models import (
    EmployeeQualification,
    EmployeeQualificationStatus,
    FederalChargeCode,
    FederalChargeCodeStatus,
)
from app.modules.people.models import Employee, EmployeeStatus
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.projects.models import Project
from app.modules.scheduling.models import ScheduleActivity, ScheduleAssignment
from app.modules.timekeeping import repository
from app.modules.timekeeping.events import (
    TIME_CORRECTION_COMPLETED,
    TIME_CORRECTION_REQUESTED,
    TIME_ENTRY_APPROVED,
    TIME_ENTRY_CERTIFIED,
    TIME_ENTRY_CREATED,
)
from app.modules.timekeeping.models import (
    TimeCorrection,
    TimeCorrectionStatus,
    TimeEntry,
    TimeEntryStatus,
)
from app.modules.timekeeping.permissions import (
    TIME_APPROVE_TEAM,
    TIME_CERTIFY_OWN,
    TIME_CORRECT_OWN,
    TIME_CORRECT_TEAM,
    TIME_ENTER_OWN,
    TIME_ENTER_TEAM,
    TIME_READ_TEAM,
)
from app.modules.timekeeping.schemas import (
    TimeApproval,
    TimeCertification,
    TimeCorrectionCreate,
    TimeEntryCreate,
)

HOUR = Decimal("3600")
CENTIHOUR = Decimal("0.01")


async def create_entry(
    session: AsyncSession,
    principal: Principal,
    data: TimeEntryCreate,
) -> TimeEntry:
    employee = await _entry_employee(session, principal, data.employee_id)
    data = await _canonical_federal_entry(session, principal, employee, data)
    existing = await repository.get_by_operation(
        session,
        principal.tenant_id,
        data.client_operation_id,
    )
    if existing is not None:
        if existing.employee_id != employee.id:
            raise HTTPException(status_code=409, detail="Offline operation ID is already in use")
        return existing
    total_hours = await _validate_entry_data(session, principal, employee, data)
    entry = TimeEntry(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        employee_id=employee.id,
        total_hours=total_hours,
        **data.model_dump(exclude={"employee_id"}),
    )
    session.add(entry)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "TimeEntry",
        entry.id,
        "created",
        correlation_id,
        None,
        _audit_state(entry),
    )
    add_outbox(
        session,
        principal,
        TIME_ENTRY_CREATED,
        "TimeEntry",
        entry.id,
        correlation_id,
        f"time-entry-created:{entry.id}",
        {"time_entry_id": str(entry.id), "employee_id": str(employee.id)},
    )
    await session.commit()
    return entry


async def request_correction(
    session: AsyncSession,
    principal: Principal,
    entry_id: uuid.UUID,
    expected_version: int,
    data: TimeCorrectionCreate,
) -> tuple[TimeCorrection, TimeEntry]:
    original = await repository.get_entry(
        session,
        principal.tenant_id,
        entry_id,
        for_update=True,
    )
    if original is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    await _authorize_correction(session, principal, original)
    existing = await repository.get_correction_by_original(
        session,
        principal.tenant_id,
        original.id,
    )
    if existing is not None:
        replacement = await repository.get_entry(
            session,
            principal.tenant_id,
            existing.replacement_entry_id,
        )
        if (
            replacement is not None
            and replacement.client_operation_id == data.replacement.client_operation_id
        ):
            return existing, replacement
        raise HTTPException(status_code=409, detail="Time entry already has a correction")
    if original.version != expected_version:
        raise HTTPException(status_code=409, detail="Time entry version conflict")
    if original.status not in {TimeEntryStatus.CERTIFIED, TimeEntryStatus.APPROVED}:
        raise HTTPException(
            status_code=409,
            detail="Only certified or approved time can be corrected",
        )
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == principal.tenant_id,
            Employee.id == original.employee_id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=409, detail="Time entry employee is unavailable")
    replacement_data = data.replacement.model_copy(update={"employee_id": employee.id})
    replacement_data = await _canonical_federal_entry(
        session,
        principal,
        employee,
        replacement_data,
    )
    existing_operation = await repository.get_by_operation(
        session,
        principal.tenant_id,
        replacement_data.client_operation_id,
    )
    if existing_operation is not None:
        raise HTTPException(status_code=409, detail="Offline operation ID is already in use")
    before = _audit_state(original)
    original.status = TimeEntryStatus.CORRECTED
    original.updated_by = principal.user_id
    original.version += 1
    await session.flush()
    total_hours = await _validate_entry_data(
        session,
        principal,
        employee,
        replacement_data,
    )
    replacement = TimeEntry(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        employee_id=employee.id,
        total_hours=total_hours,
        **replacement_data.model_dump(exclude={"employee_id"}),
    )
    session.add(replacement)
    await session.flush()
    correction = TimeCorrection(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        original_entry_id=original.id,
        replacement_entry_id=replacement.id,
        reason=data.reason,
        requested_by=principal.user_id,
    )
    session.add(correction)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "TimeEntry",
        original.id,
        "correction_requested",
        correlation_id,
        before,
        _audit_state(original),
        data.reason,
    )
    add_audit(
        session,
        principal,
        "TimeEntry",
        replacement.id,
        "correction_replacement_created",
        correlation_id,
        None,
        _audit_state(replacement),
        data.reason,
    )
    add_audit(
        session,
        principal,
        "TimeCorrection",
        correction.id,
        "created",
        correlation_id,
        None,
        _correction_audit_state(correction),
        data.reason,
    )
    add_outbox(
        session,
        principal,
        TIME_CORRECTION_REQUESTED,
        "TimeCorrection",
        correction.id,
        correlation_id,
        f"time-correction-requested:{correction.id}",
        {
            "correction_id": str(correction.id),
            "original_entry_id": str(original.id),
            "replacement_entry_id": str(replacement.id),
        },
    )
    await session.commit()
    return correction, replacement


async def certify_entry(
    session: AsyncSession,
    principal: Principal,
    entry_id: uuid.UUID,
    expected_version: int,
    data: TimeCertification,
) -> TimeEntry:
    principal.require(TIME_CERTIFY_OWN)
    entry = await _transition_entry(session, principal, entry_id, expected_version)
    employee = await _own_employee(session, principal)
    if entry.employee_id != employee.id:
        raise HTTPException(status_code=403, detail="Employees may certify only their own time")
    if entry.status is not TimeEntryStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft time can be certified")
    before = _audit_state(entry)
    entry.status = TimeEntryStatus.CERTIFIED
    entry.certified_at = datetime.now(UTC)
    entry.certified_by = principal.user_id
    entry.certification_statement = data.statement
    entry.updated_by = principal.user_id
    entry.version += 1
    correction = await repository.get_correction_by_replacement(
        session,
        principal.tenant_id,
        entry.id,
        for_update=True,
    )
    correction_before = (
        _correction_audit_state(correction) if correction is not None else None
    )
    if correction is not None:
        correction.status = TimeCorrectionStatus.PENDING_APPROVAL
        correction.updated_by = principal.user_id
        correction.version += 1
    await _record_transition(
        session,
        principal,
        entry,
        "employee_certified",
        TIME_ENTRY_CERTIFIED,
        before,
        data.statement,
        correction,
        correction_before,
    )
    return entry


async def approve_entry(
    session: AsyncSession,
    principal: Principal,
    entry_id: uuid.UUID,
    expected_version: int,
    data: TimeApproval,
) -> TimeEntry:
    principal.require(TIME_APPROVE_TEAM)
    entry = await _transition_entry(session, principal, entry_id, expected_version)
    if entry.status is not TimeEntryStatus.CERTIFIED:
        raise HTTPException(status_code=409, detail="Certified time is required")
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == principal.tenant_id,
            Employee.id == entry.employee_id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=409, detail="Time entry employee is unavailable")
    if employee.user_id == principal.user_id:
        raise HTTPException(status_code=403, detail="Employees cannot approve their own time")
    before = _audit_state(entry)
    entry.status = TimeEntryStatus.APPROVED
    entry.approved_at = datetime.now(UTC)
    entry.approved_by = principal.user_id
    entry.updated_by = principal.user_id
    entry.version += 1
    correction = await repository.get_correction_by_replacement(
        session,
        principal.tenant_id,
        entry.id,
        for_update=True,
    )
    correction_before = (
        _correction_audit_state(correction) if correction is not None else None
    )
    if correction is not None:
        correction.status = TimeCorrectionStatus.COMPLETED
        correction.completed_at = datetime.now(UTC)
        correction.updated_by = principal.user_id
        correction.version += 1
    await _record_transition(
        session,
        principal,
        entry,
        "supervisor_approved",
        TIME_ENTRY_APPROVED,
        before,
        data.reason,
        correction,
        correction_before,
    )
    return entry


async def list_entries(
    session: AsyncSession,
    principal: Principal,
    employee_id: uuid.UUID | None,
    date_from: date,
    date_to: date,
) -> list[TimeEntry]:
    if date_to < date_from or (date_to - date_from).days > 92:
        raise HTTPException(status_code=422, detail="Time-entry date range is invalid")
    if TIME_READ_TEAM not in principal.permissions:
        own = await _own_employee(session, principal)
        employee_id = own.id
    return await repository.list_entries(
        session,
        principal.tenant_id,
        employee_id,
        date_from,
        date_to,
    )


async def list_entry_employee_options(
    session: AsyncSession,
    principal: Principal,
) -> list[Employee]:
    if TIME_ENTER_TEAM in principal.permissions or TIME_READ_TEAM in principal.permissions:
        return list(
            await session.scalars(
                select(Employee)
                .where(
                    Employee.tenant_id == principal.tenant_id,
                    Employee.status == EmployeeStatus.ACTIVE,
                )
                .order_by(Employee.last_name, Employee.first_name)
            )
        )
    principal.require(TIME_ENTER_OWN)
    return [await _own_employee(session, principal)]


async def _entry_employee(
    session: AsyncSession,
    principal: Principal,
    requested_employee_id: uuid.UUID | None,
) -> Employee:
    if TIME_ENTER_TEAM in principal.permissions and requested_employee_id is not None:
        employee = await session.scalar(
            select(Employee).where(
                Employee.tenant_id == principal.tenant_id,
                Employee.id == requested_employee_id,
            )
        )
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        return employee
    principal.require(TIME_ENTER_OWN)
    own = await _own_employee(session, principal)
    if requested_employee_id is not None and requested_employee_id != own.id:
        raise HTTPException(status_code=403, detail="Employees may enter only their own time")
    return own


async def _own_employee(session: AsyncSession, principal: Principal) -> Employee:
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == principal.tenant_id,
            Employee.user_id == principal.user_id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=403, detail="Employee profile is not linked")
    return employee


async def _transition_entry(
    session: AsyncSession,
    principal: Principal,
    entry_id: uuid.UUID,
    expected_version: int,
) -> TimeEntry:
    entry = await repository.get_entry(
        session,
        principal.tenant_id,
        entry_id,
        for_update=True,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    if entry.version != expected_version:
        raise HTTPException(status_code=409, detail="Time entry version conflict")
    return entry


async def _validate_project(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    project = await session.scalar(
        select(Project.id).where(
            Project.tenant_id == tenant_id,
            Project.id == project_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")


async def _validate_assignment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    assignment_id: uuid.UUID,
    employee_id: uuid.UUID,
    project_id: uuid.UUID | None,
) -> None:
    assignment = await session.execute(
        select(ScheduleAssignment, ScheduleActivity)
        .join(
            ScheduleActivity,
            (ScheduleActivity.tenant_id == ScheduleAssignment.tenant_id)
            & (ScheduleActivity.id == ScheduleAssignment.activity_id),
        )
        .where(
            ScheduleAssignment.tenant_id == tenant_id,
            ScheduleAssignment.id == assignment_id,
            ScheduleAssignment.employee_id == employee_id,
        )
    )
    row = assignment.first()
    if row is None:
        raise HTTPException(status_code=409, detail="Schedule assignment is invalid")
    _, activity = row
    if project_id is None:
        raise HTTPException(status_code=422, detail="Scheduled time requires a project")
    if activity.project_id != project_id:
        raise HTTPException(
            status_code=409,
            detail="Schedule assignment does not belong to the selected project",
        )


async def _authorize_correction(
    session: AsyncSession,
    principal: Principal,
    entry: TimeEntry,
) -> None:
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == principal.tenant_id,
            Employee.id == entry.employee_id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=409, detail="Time entry employee is unavailable")
    if employee.user_id == principal.user_id:
        principal.require(TIME_CORRECT_OWN)
        return
    principal.require(TIME_CORRECT_TEAM)


async def _validate_entry_data(
    session: AsyncSession,
    principal: Principal,
    employee: Employee,
    data: TimeEntryCreate,
) -> Decimal:
    await _lock_employee_day(session, principal.tenant_id, employee.id, data.work_date)
    conflict = await repository.find_overlap(
        session,
        principal.tenant_id,
        employee.id,
        data.start_at,
        data.end_at,
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="Time entry overlaps an existing record")
    total_hours = _duration_hours(data.start_at, data.end_at, data.break_minutes)
    classified_hours = sum(
        (
            data.regular_hours,
            data.overtime_hours,
            data.double_time_hours,
            data.travel_hours,
            data.leave_hours,
            data.indirect_hours,
        ),
        Decimal("0.00"),
    )
    if classified_hours != total_hours:
        raise HTTPException(
            status_code=422,
            detail=f"Classified hours must equal elapsed hours ({total_hours})",
        )
    if data.project_id is not None:
        await _validate_project(session, principal.tenant_id, data.project_id)
        if data.start_at > datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Future direct time is not allowed")
    if data.schedule_assignment_id is not None:
        await _validate_assignment(
            session,
            principal.tenant_id,
            data.schedule_assignment_id,
            employee.id,
            data.project_id,
        )
    if data.original_device_timestamp > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Device timestamp is in the future")
    if data.work_date < date.today() - timedelta(days=1) and not data.late_reason:
        raise HTTPException(status_code=422, detail="Late time requires an explanation")
    return total_hours


async def _canonical_federal_entry(
    session: AsyncSession,
    principal: Principal,
    employee: Employee,
    data: TimeEntryCreate,
) -> TimeEntryCreate:
    if data.federal_charge_code_id is None:
        return data
    charge_code = await session.scalar(
        select(FederalChargeCode).where(
            FederalChargeCode.tenant_id == principal.tenant_id,
            FederalChargeCode.id == data.federal_charge_code_id,
        )
    )
    if charge_code is None:
        raise HTTPException(status_code=404, detail="Federal charge code not found")
    if (
        charge_code.status is not FederalChargeCodeStatus.OPEN
        or charge_code.active_from > data.work_date
        or (
            charge_code.active_to is not None
            and charge_code.active_to < data.work_date
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Federal charge code is closed or not effective for the work date",
        )
    _match_federal_value("charge code", data.charge_code, charge_code.code)
    _match_federal_value("contract", data.contract_code, charge_code.contract_code)
    _match_federal_value("task order", data.task_order, charge_code.task_order)
    _match_federal_value("CLIN", data.clin, charge_code.clin)
    _match_federal_value("funding line", data.funding_line, charge_code.funding_line)
    _match_federal_value("cost code", data.cost_code, charge_code.cost_code)
    _match_federal_value(
        "labor category",
        data.labor_category,
        charge_code.labor_category,
    )
    if (
        charge_code.project_id is not None
        and data.project_id is not None
        and data.project_id != charge_code.project_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Federal charge code does not belong to the selected project",
        )
    if charge_code.required_qualification_code:
        qualification = await session.scalar(
            select(EmployeeQualification.id).where(
                EmployeeQualification.tenant_id == principal.tenant_id,
                EmployeeQualification.employee_id == employee.id,
                EmployeeQualification.qualification_code
                == charge_code.required_qualification_code,
                EmployeeQualification.status == EmployeeQualificationStatus.ACTIVE,
                EmployeeQualification.effective_from <= data.work_date,
                or_(
                    EmployeeQualification.effective_to.is_(None),
                    EmployeeQualification.effective_to >= data.work_date,
                ),
            )
        )
        if qualification is None:
            raise HTTPException(
                status_code=409,
                detail="Employee qualification is not valid for this federal charge code",
            )
    return data.model_copy(
        update={
            "project_id": charge_code.project_id or data.project_id,
            "contract_code": charge_code.contract_code,
            "task_order": charge_code.task_order,
            "clin": charge_code.clin,
            "funding_line": charge_code.funding_line,
            "charge_code": charge_code.code,
            "cost_code": charge_code.cost_code,
            "labor_category": charge_code.labor_category,
        }
    )


def _match_federal_value(label: str, submitted: str | None, canonical: str | None) -> None:
    if submitted is not None and submitted != canonical:
        raise HTTPException(
            status_code=409,
            detail=f"Submitted {label} does not match the canonical federal charge code",
        )


async def _record_transition(
    session: AsyncSession,
    principal: Principal,
    entry: TimeEntry,
    action: str,
    event_type: str,
    before: dict[str, str],
    reason: str,
    correction: TimeCorrection | None = None,
    correction_before: dict[str, str] | None = None,
) -> None:
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "TimeEntry",
        entry.id,
        action,
        correlation_id,
        before,
        _audit_state(entry),
        reason,
    )
    add_outbox(
        session,
        principal,
        event_type,
        "TimeEntry",
        entry.id,
        correlation_id,
        f"{event_type.lower()}:{entry.id}:{entry.version}",
        {"time_entry_id": str(entry.id), "employee_id": str(entry.employee_id)},
    )
    if correction is not None:
        correction_action = (
            "completed"
            if correction.status is TimeCorrectionStatus.COMPLETED
            else "replacement_certified"
        )
        add_audit(
            session,
            principal,
            "TimeCorrection",
            correction.id,
            correction_action,
            correlation_id,
            correction_before,
            _correction_audit_state(correction),
            reason,
        )
        if correction.status is TimeCorrectionStatus.COMPLETED:
            add_outbox(
                session,
                principal,
                TIME_CORRECTION_COMPLETED,
                "TimeCorrection",
                correction.id,
                correlation_id,
                f"time-correction-completed:{correction.id}:{correction.version}",
                {
                    "correction_id": str(correction.id),
                    "replacement_entry_id": str(entry.id),
                },
            )
    await session.commit()


async def _lock_employee_day(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    work_date: date,
) -> None:
    digest = hashlib.sha256(f"{tenant_id}:{employee_id}:{work_date}".encode()).digest()[:8]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, signed=True)},
    )


def _duration_hours(start_at: datetime, end_at: datetime, break_minutes: int) -> Decimal:
    seconds = Decimal(str((end_at - start_at).total_seconds() - break_minutes * 60))
    if seconds < 0:
        raise HTTPException(status_code=422, detail="Break exceeds elapsed time")
    return (seconds / HOUR).quantize(CENTIHOUR, rounding=ROUND_HALF_UP)


def _audit_state(entry: TimeEntry) -> dict[str, str]:
    return {
        "employee_id": str(entry.employee_id),
        "work_date": str(entry.work_date),
        "total_hours": str(entry.total_hours),
        "charge_code": entry.charge_code,
        "federal_charge_code_id": str(entry.federal_charge_code_id or ""),
        "contract_code": entry.contract_code or "",
        "labor_category": entry.labor_category or "",
        "status": entry.status,
        "version": str(entry.version),
    }


def _correction_audit_state(correction: TimeCorrection) -> dict[str, str]:
    return {
        "original_entry_id": str(correction.original_entry_id),
        "replacement_entry_id": str(correction.replacement_entry_id),
        "status": correction.status,
        "version": str(correction.version),
    }
