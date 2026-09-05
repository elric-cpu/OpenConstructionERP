import hashlib
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import correlation_uuid
from app.core.security import Principal
from app.modules.people.models import Employee, EmployeeStatus
from app.modules.platform.audit import add_audit, add_outbox
from app.modules.projects.models import Project
from app.modules.scheduling import repository
from app.modules.scheduling.events import (
    EMPLOYEE_SCHEDULED,
    SCHEDULE_ACTIVITY_CREATED,
    SCHEDULE_CREATED,
)
from app.modules.scheduling.models import Schedule, ScheduleActivity, ScheduleAssignment
from app.modules.scheduling.permissions import (
    SCHEDULES_MANAGE,
    SCHEDULES_READ,
    SCHEDULES_READ_OWN,
)
from app.modules.scheduling.schemas import (
    ActivityCreate,
    AssignmentCreate,
    ScheduleCreate,
    ScheduleEntryRead,
)


async def create_schedule(
    session: AsyncSession,
    principal: Principal,
    data: ScheduleCreate,
) -> Schedule:
    principal.require(SCHEDULES_MANAGE)
    project = await session.scalar(
        select(Project).where(
            Project.tenant_id == principal.tenant_id,
            Project.id == data.project_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    schedule = Schedule(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        **data.model_dump(),
    )
    session.add(schedule)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project already has a schedule",
        ) from exc
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "Schedule",
        schedule.id,
        "created",
        correlation_id,
        None,
        {"project_id": str(schedule.project_id), "timezone": schedule.timezone},
    )
    add_outbox(
        session,
        principal,
        SCHEDULE_CREATED,
        "Schedule",
        schedule.id,
        correlation_id,
        f"schedule-created:{schedule.id}",
        {"schedule_id": str(schedule.id), "project_id": str(schedule.project_id)},
    )
    await session.commit()
    return schedule


async def get_project_schedule(
    session: AsyncSession,
    principal: Principal,
    project_id: uuid.UUID,
) -> Schedule:
    if not ({SCHEDULES_READ, SCHEDULES_MANAGE} & principal.permissions):
        principal.require(SCHEDULES_READ)
    schedule = await repository.get_project_schedule(
        session,
        principal.tenant_id,
        project_id,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Project schedule not found")
    return schedule


async def create_activity(
    session: AsyncSession,
    principal: Principal,
    schedule_id: uuid.UUID,
    expected_version: int,
    data: ActivityCreate,
) -> ScheduleActivity:
    principal.require(SCHEDULES_MANAGE)
    schedule = await repository.get_schedule(
        session,
        principal.tenant_id,
        schedule_id,
        for_update=True,
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if schedule.version != expected_version:
        raise HTTPException(status_code=409, detail="Schedule version conflict")
    activity = ScheduleActivity(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        schedule_id=schedule.id,
        project_id=schedule.project_id,
        **data.model_dump(),
    )
    schedule.version += 1
    schedule.updated_by = principal.user_id
    session.add(activity)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "ScheduleActivity",
        activity.id,
        "created",
        correlation_id,
        None,
        _activity_state(activity),
    )
    add_outbox(
        session,
        principal,
        SCHEDULE_ACTIVITY_CREATED,
        "ScheduleActivity",
        activity.id,
        correlation_id,
        f"schedule-activity-created:{activity.id}",
        {"activity_id": str(activity.id), "schedule_id": str(schedule.id)},
    )
    await session.commit()
    return activity


async def assign_employee(
    session: AsyncSession,
    principal: Principal,
    activity_id: uuid.UUID,
    expected_version: int,
    data: AssignmentCreate,
) -> ScheduleAssignment:
    principal.require(SCHEDULES_MANAGE)
    activity = await repository.get_activity(
        session,
        principal.tenant_id,
        activity_id,
        for_update=True,
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Schedule activity not found")
    if activity.version != expected_version:
        raise HTTPException(status_code=409, detail="Schedule activity version conflict")
    employee = await session.scalar(
        select(Employee).where(
            Employee.tenant_id == principal.tenant_id,
            Employee.id == data.employee_id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    if employee.status not in {EmployeeStatus.IDENTITY_CREATED, EmployeeStatus.ACTIVE}:
        raise HTTPException(status_code=409, detail="Employee is not available for scheduling")
    await _lock_employee_schedule(session, principal.tenant_id, employee.id)
    existing = await session.scalar(
        select(ScheduleAssignment).where(
            ScheduleAssignment.tenant_id == principal.tenant_id,
            ScheduleAssignment.activity_id == activity.id,
            ScheduleAssignment.employee_id == employee.id,
        )
    )
    if existing is not None:
        return existing
    conflict = await repository.find_conflict(
        session,
        principal.tenant_id,
        employee.id,
        activity.start_at,
        activity.end_at,
    )
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Employee has a conflicting assignment: {conflict.title}",
        )
    assignment = ScheduleAssignment(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        activity_id=activity.id,
        employee_id=employee.id,
        assignment_role=data.assignment_role,
    )
    activity.version += 1
    activity.updated_by = principal.user_id
    session.add(assignment)
    await session.flush()
    correlation_id = correlation_uuid()
    add_audit(
        session,
        principal,
        "ScheduleAssignment",
        assignment.id,
        "employee_assigned",
        correlation_id,
        None,
        {
            "activity_id": str(activity.id),
            "employee_id": str(employee.id),
            "start_at": activity.start_at.isoformat(),
            "end_at": activity.end_at.isoformat(),
        },
        data.reason,
    )
    add_outbox(
        session,
        principal,
        EMPLOYEE_SCHEDULED,
        "ScheduleAssignment",
        assignment.id,
        correlation_id,
        f"employee-scheduled:{assignment.id}",
        {
            "assignment_id": str(assignment.id),
            "activity_id": str(activity.id),
            "employee_id": str(employee.id),
        },
    )
    await session.commit()
    return assignment


async def list_entries(
    session: AsyncSession,
    principal: Principal,
    start_at: datetime,
    end_at: datetime,
    employee_id: uuid.UUID | None,
) -> list[ScheduleEntryRead]:
    if (
        start_at.tzinfo is None
        or start_at.utcoffset() is None
        or end_at.tzinfo is None
        or end_at.utcoffset() is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Schedule timestamps must include a timezone",
        )
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="Schedule window is invalid")
    if SCHEDULES_READ not in principal.permissions:
        principal.require(SCHEDULES_READ_OWN)
        own_employee = await session.scalar(
            select(Employee).where(
                Employee.tenant_id == principal.tenant_id,
                Employee.user_id == principal.user_id,
            )
        )
        if own_employee is None:
            raise HTTPException(status_code=403, detail="Employee profile is not linked")
        employee_id = own_employee.id
    rows = await session.execute(
        repository.entries_statement(
            principal.tenant_id,
            start_at,
            end_at,
            employee_id,
        )
    )
    return [
        ScheduleEntryRead.model_validate(
            {
                "activity": activity,
                "assignment": assignment,
                "employee_name": (
                    f"{employee.first_name} {employee.last_name}" if employee else None
                ),
                "project_name": project.name,
            }
        )
        for activity, assignment, employee, project in rows
    ]


async def _lock_employee_schedule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    digest = hashlib.sha256(f"{tenant_id}:{employee_id}".encode()).digest()[:8]
    lock_key = int.from_bytes(digest, signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})


def _activity_state(activity: ScheduleActivity) -> dict[str, str]:
    return {
        "schedule_id": str(activity.schedule_id),
        "project_id": str(activity.project_id),
        "title": activity.title,
        "start_at": activity.start_at.isoformat(),
        "end_at": activity.end_at.isoformat(),
        "status": activity.status,
    }
