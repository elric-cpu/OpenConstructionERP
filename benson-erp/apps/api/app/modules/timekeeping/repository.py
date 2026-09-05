import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.timekeeping.models import TimeCorrection, TimeEntry, TimeEntryStatus


async def get_entry(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entry_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> TimeEntry | None:
    statement = select(TimeEntry).where(
        TimeEntry.tenant_id == tenant_id,
        TimeEntry.id == entry_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def get_by_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    operation_id: uuid.UUID,
) -> TimeEntry | None:
    return await session.scalar(
        select(TimeEntry).where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.client_operation_id == operation_id,
        )
    )


async def get_correction_by_original(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    original_entry_id: uuid.UUID,
) -> TimeCorrection | None:
    return await session.scalar(
        select(TimeCorrection).where(
            TimeCorrection.tenant_id == tenant_id,
            TimeCorrection.original_entry_id == original_entry_id,
        )
    )


async def get_correction_by_replacement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    replacement_entry_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> TimeCorrection | None:
    statement = select(TimeCorrection).where(
        TimeCorrection.tenant_id == tenant_id,
        TimeCorrection.replacement_entry_id == replacement_entry_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def find_overlap(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
) -> TimeEntry | None:
    return await session.scalar(
        select(TimeEntry)
        .where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.employee_id == employee_id,
            TimeEntry.status != TimeEntryStatus.CORRECTED,
            TimeEntry.start_at < end_at,
            TimeEntry.end_at > start_at,
        )
        .limit(1)
    )


async def list_entries(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    date_from: date,
    date_to: date,
) -> list[TimeEntry]:
    statement = (
        select(TimeEntry)
        .where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.work_date >= date_from,
            TimeEntry.work_date <= date_to,
        )
        .order_by(TimeEntry.work_date.desc(), TimeEntry.start_at)
    )
    if employee_id is not None:
        statement = statement.where(TimeEntry.employee_id == employee_id)
    return list(await session.scalars(statement))
