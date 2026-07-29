import uuid
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payroll.models import (
    EmployeePayRate,
    PayrollExport,
    PayrollExportFormat,
    PayrollMappingType,
    PayrollPeriod,
    PayrollProviderMapping,
)
from app.modules.people.models import Employee
from app.modules.timekeeping.models import TimeEntry, TimeEntryStatus


async def get_period(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> PayrollPeriod | None:
    statement = select(PayrollPeriod).where(
        PayrollPeriod.tenant_id == tenant_id,
        PayrollPeriod.id == period_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def list_periods(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[PayrollPeriod]:
    return list(
        await session.scalars(
            select(PayrollPeriod)
            .where(PayrollPeriod.tenant_id == tenant_id)
            .order_by(PayrollPeriod.period_start.desc())
        )
    )


async def list_mappings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str | None = None,
) -> list[PayrollProviderMapping]:
    statement = select(PayrollProviderMapping).where(
        PayrollProviderMapping.tenant_id == tenant_id
    )
    if provider is not None:
        statement = statement.where(PayrollProviderMapping.provider == provider)
    return list(
        await session.scalars(
            statement.order_by(
                PayrollProviderMapping.provider,
                PayrollProviderMapping.mapping_type,
                PayrollProviderMapping.internal_key,
                PayrollProviderMapping.effective_from.desc(),
            )
        )
    )


async def list_pay_rates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[EmployeePayRate]:
    return list(
        await session.scalars(
            select(EmployeePayRate)
            .where(EmployeePayRate.tenant_id == tenant_id)
            .order_by(EmployeePayRate.employee_id, EmployeePayRate.effective_from.desc())
        )
    )


async def find_overlapping_period(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> PayrollPeriod | None:
    return await session.scalar(
        select(PayrollPeriod)
        .where(
            PayrollPeriod.tenant_id == tenant_id,
            PayrollPeriod.period_start <= period_end,
            PayrollPeriod.period_end >= period_start,
        )
        .limit(1)
    )


async def period_time(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period: PayrollPeriod,
) -> list[tuple[TimeEntry, Employee]]:
    return list(
        (
            await session.execute(
                select(TimeEntry, Employee)
                .join(
                    Employee,
                    and_(
                        Employee.tenant_id == TimeEntry.tenant_id,
                        Employee.id == TimeEntry.employee_id,
                    ),
                )
                .where(
                    TimeEntry.tenant_id == tenant_id,
                    TimeEntry.work_date >= period.period_start,
                    TimeEntry.work_date <= period.period_end,
                    TimeEntry.status != TimeEntryStatus.CORRECTED,
                )
                .order_by(Employee.employee_number, TimeEntry.work_date, TimeEntry.start_at)
            )
        ).tuples().all()
    )


async def active_mapping(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    mapping_type: PayrollMappingType,
    internal_key: str,
    effective_date: date,
) -> PayrollProviderMapping | None:
    return await session.scalar(
        select(PayrollProviderMapping)
        .where(
            PayrollProviderMapping.tenant_id == tenant_id,
            PayrollProviderMapping.provider == provider,
            PayrollProviderMapping.mapping_type == mapping_type,
            PayrollProviderMapping.internal_key == internal_key,
            PayrollProviderMapping.effective_from <= effective_date,
            or_(
                PayrollProviderMapping.effective_to.is_(None),
                PayrollProviderMapping.effective_to >= effective_date,
            ),
        )
        .order_by(PayrollProviderMapping.effective_from.desc())
        .limit(1)
    )


async def period_mappings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider: str,
    period_start: date,
    period_end: date,
) -> list[PayrollProviderMapping]:
    return list(
        await session.scalars(
            select(PayrollProviderMapping).where(
                PayrollProviderMapping.tenant_id == tenant_id,
                PayrollProviderMapping.provider == provider,
                PayrollProviderMapping.effective_from <= period_end,
                or_(
                    PayrollProviderMapping.effective_to.is_(None),
                    PayrollProviderMapping.effective_to >= period_start,
                ),
            )
        )
    )


async def active_pay_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    effective_date: date,
) -> EmployeePayRate | None:
    return await session.scalar(
        select(EmployeePayRate)
        .where(
            EmployeePayRate.tenant_id == tenant_id,
            EmployeePayRate.employee_id == employee_id,
            EmployeePayRate.effective_from <= effective_date,
            or_(
                EmployeePayRate.effective_to.is_(None),
                EmployeePayRate.effective_to >= effective_date,
            ),
        )
        .order_by(EmployeePayRate.effective_from.desc())
        .limit(1)
    )


async def period_pay_rates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[EmployeePayRate]:
    return list(
        await session.scalars(
            select(EmployeePayRate).where(
                EmployeePayRate.tenant_id == tenant_id,
                EmployeePayRate.effective_from <= period_end,
                or_(
                    EmployeePayRate.effective_to.is_(None),
                    EmployeePayRate.effective_to >= period_start,
                ),
            )
        )
    )


async def find_export(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_id: uuid.UUID,
    provider: str,
    export_format: PayrollExportFormat,
    artifact_version: int = 1,
) -> PayrollExport | None:
    return await session.scalar(
        select(PayrollExport).where(
            PayrollExport.tenant_id == tenant_id,
            PayrollExport.payroll_period_id == period_id,
            PayrollExport.provider == provider,
            PayrollExport.format == export_format,
            PayrollExport.artifact_version == artifact_version,
        )
    )


async def get_export(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    export_id: uuid.UUID,
) -> PayrollExport | None:
    return await session.scalar(
        select(PayrollExport).where(
            PayrollExport.tenant_id == tenant_id,
            PayrollExport.id == export_id,
        )
    )


async def list_exports(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_id: uuid.UUID,
) -> list[PayrollExport]:
    return list(
        await session.scalars(
            select(PayrollExport)
            .where(
                PayrollExport.tenant_id == tenant_id,
                PayrollExport.payroll_period_id == period_id,
            )
            .order_by(PayrollExport.generated_at.desc())
        )
    )
