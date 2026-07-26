import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.people.models import Employee
from app.modules.projects.models import Project
from app.modules.scheduling.models import (
    ActivityStatus,
    Schedule,
    ScheduleActivity,
    ScheduleAssignment,
)


async def get_schedule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    schedule_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> Schedule | None:
    statement = select(Schedule).where(
        Schedule.tenant_id == tenant_id,
        Schedule.id == schedule_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def get_project_schedule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Schedule | None:
    return await session.scalar(
        select(Schedule).where(
            Schedule.tenant_id == tenant_id,
            Schedule.project_id == project_id,
        )
    )


async def get_activity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> ScheduleActivity | None:
    statement = select(ScheduleActivity).where(
        ScheduleActivity.tenant_id == tenant_id,
        ScheduleActivity.id == activity_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def find_conflict(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
) -> ScheduleActivity | None:
    return await session.scalar(
        select(ScheduleActivity)
        .join(
            ScheduleAssignment,
            (ScheduleAssignment.tenant_id == ScheduleActivity.tenant_id)
            & (ScheduleAssignment.activity_id == ScheduleActivity.id),
        )
        .where(
            ScheduleAssignment.tenant_id == tenant_id,
            ScheduleAssignment.employee_id == employee_id,
            ScheduleActivity.status != ActivityStatus.CANCELLED,
            ScheduleActivity.start_at < end_at,
            ScheduleActivity.end_at > start_at,
        )
        .limit(1)
    )


def entries_statement(
    tenant_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    employee_id: uuid.UUID | None,
) -> Select[tuple[ScheduleActivity, ScheduleAssignment | None, Employee | None, Project]]:
    statement = (
        select(ScheduleActivity, ScheduleAssignment, Employee, Project)
        .join(
            Project,
            (Project.tenant_id == ScheduleActivity.tenant_id)
            & (Project.id == ScheduleActivity.project_id),
        )
        .outerjoin(
            ScheduleAssignment,
            (ScheduleAssignment.tenant_id == ScheduleActivity.tenant_id)
            & (ScheduleAssignment.activity_id == ScheduleActivity.id),
        )
        .outerjoin(
            Employee,
            (Employee.tenant_id == ScheduleAssignment.tenant_id)
            & (Employee.id == ScheduleAssignment.employee_id),
        )
        .where(
            ScheduleActivity.tenant_id == tenant_id,
            ScheduleActivity.start_at < end_at,
            ScheduleActivity.end_at > start_at,
        )
        .order_by(ScheduleActivity.start_at, ScheduleActivity.title)
    )
    if employee_id is not None:
        statement = statement.where(ScheduleAssignment.employee_id == employee_id)
    return cast(
        Select[
            tuple[
                ScheduleActivity,
                ScheduleAssignment | None,
                Employee | None,
                Project,
            ]
        ],
        statement,
    )
