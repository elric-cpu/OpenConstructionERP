import uuid
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.federal_labor.models import (
    EmployeeQualification,
    EmployeeQualificationStatus,
    FederalChargeCode,
    FederalInvoiceSupport,
    FederalInvoiceSupportLine,
    FederalLaborRate,
)
from app.modules.payroll.models import PayrollResultImport, PayrollResultLine
from app.modules.people.models import Employee
from app.modules.timekeeping.models import TimeEntry, TimeEntryStatus


async def get_charge_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    charge_code_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> FederalChargeCode | None:
    statement = select(FederalChargeCode).where(
        FederalChargeCode.tenant_id == tenant_id,
        FederalChargeCode.id == charge_code_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def list_charge_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[FederalChargeCode]:
    return list(
        await session.scalars(
            select(FederalChargeCode)
            .where(FederalChargeCode.tenant_id == tenant_id)
            .order_by(
                FederalChargeCode.contract_code,
                FederalChargeCode.task_order,
                FederalChargeCode.code,
            )
        )
    )


async def get_charge_code_by_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    code: str,
) -> FederalChargeCode | None:
    return await session.scalar(
        select(FederalChargeCode).where(
            FederalChargeCode.tenant_id == tenant_id,
            FederalChargeCode.code == code,
        )
    )


async def get_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rate_id: uuid.UUID,
) -> FederalLaborRate | None:
    return await session.scalar(
        select(FederalLaborRate).where(
            FederalLaborRate.tenant_id == tenant_id,
            FederalLaborRate.id == rate_id,
        )
    )


async def list_rates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    charge_code_id: uuid.UUID | None = None,
) -> list[FederalLaborRate]:
    statement = select(FederalLaborRate).where(FederalLaborRate.tenant_id == tenant_id)
    if charge_code_id is not None:
        statement = statement.where(
            FederalLaborRate.federal_charge_code_id == charge_code_id
        )
    return list(
        await session.scalars(
            statement.order_by(
                FederalLaborRate.federal_charge_code_id,
                FederalLaborRate.labor_category,
                FederalLaborRate.effective_from.desc(),
            )
        )
    )


async def overlapping_rate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    charge_code_id: uuid.UUID,
    labor_category: str,
    effective_from: date,
    effective_to: date | None,
) -> FederalLaborRate | None:
    range_end = effective_to or date.max
    return await session.scalar(
        select(FederalLaborRate)
        .where(
            FederalLaborRate.tenant_id == tenant_id,
            FederalLaborRate.federal_charge_code_id == charge_code_id,
            FederalLaborRate.labor_category == labor_category,
            FederalLaborRate.effective_from <= range_end,
            or_(
                FederalLaborRate.effective_to.is_(None),
                FederalLaborRate.effective_to >= effective_from,
            ),
        )
        .limit(1)
    )


async def get_qualification(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    qualification_id: uuid.UUID,
) -> EmployeeQualification | None:
    return await session.scalar(
        select(EmployeeQualification).where(
            EmployeeQualification.tenant_id == tenant_id,
            EmployeeQualification.id == qualification_id,
        )
    )


async def list_qualifications(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID | None = None,
) -> list[EmployeeQualification]:
    statement = select(EmployeeQualification).where(
        EmployeeQualification.tenant_id == tenant_id
    )
    if employee_id is not None:
        statement = statement.where(EmployeeQualification.employee_id == employee_id)
    return list(
        await session.scalars(
            statement.order_by(
                EmployeeQualification.employee_id,
                EmployeeQualification.qualification_code,
                EmployeeQualification.effective_from.desc(),
            )
        )
    )


async def overlapping_qualification(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    qualification_code: str,
    effective_from: date,
    effective_to: date | None,
) -> EmployeeQualification | None:
    range_end = effective_to or date.max
    return await session.scalar(
        select(EmployeeQualification)
        .where(
            EmployeeQualification.tenant_id == tenant_id,
            EmployeeQualification.employee_id == employee_id,
            EmployeeQualification.qualification_code == qualification_code,
            EmployeeQualification.effective_from <= range_end,
            or_(
                EmployeeQualification.effective_to.is_(None),
                EmployeeQualification.effective_to >= effective_from,
            ),
        )
        .limit(1)
    )


async def period_rates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[FederalLaborRate]:
    return list(
        await session.scalars(
            select(FederalLaborRate).where(
                FederalLaborRate.tenant_id == tenant_id,
                FederalLaborRate.effective_from <= period_end,
                or_(
                    FederalLaborRate.effective_to.is_(None),
                    FederalLaborRate.effective_to >= period_start,
                ),
            )
        )
    )


async def period_qualifications(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[EmployeeQualification]:
    return list(
        await session.scalars(
            select(EmployeeQualification).where(
                EmployeeQualification.tenant_id == tenant_id,
                EmployeeQualification.status == EmployeeQualificationStatus.ACTIVE,
                EmployeeQualification.effective_from <= period_end,
                or_(
                    EmployeeQualification.effective_to.is_(None),
                    EmployeeQualification.effective_to >= period_start,
                ),
            )
        )
    )


async def invoice_time(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    contract_code: str,
    task_order: str | None,
    period_start: date,
    period_end: date,
) -> list[tuple[TimeEntry, Employee, FederalChargeCode]]:
    statement = (
        select(TimeEntry, Employee, FederalChargeCode)
        .join(
            Employee,
            and_(
                Employee.tenant_id == TimeEntry.tenant_id,
                Employee.id == TimeEntry.employee_id,
            ),
        )
        .join(
            FederalChargeCode,
            and_(
                FederalChargeCode.tenant_id == TimeEntry.tenant_id,
                FederalChargeCode.id == TimeEntry.federal_charge_code_id,
            ),
        )
        .where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.status == TimeEntryStatus.APPROVED,
            TimeEntry.work_date >= period_start,
            TimeEntry.work_date <= period_end,
            FederalChargeCode.contract_code == contract_code,
        )
        .order_by(TimeEntry.work_date, Employee.employee_number, TimeEntry.start_at)
    )
    if task_order is not None:
        statement = statement.where(FederalChargeCode.task_order == task_order)
    return list((await session.execute(statement)).tuples().all())


async def payroll_results_for_entries(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    time_entry_ids: list[uuid.UUID],
) -> list[tuple[PayrollResultLine, PayrollResultImport]]:
    if not time_entry_ids:
        return []
    return list(
        (
            await session.execute(
                select(PayrollResultLine, PayrollResultImport)
                .join(
                    PayrollResultImport,
                    and_(
                        PayrollResultImport.tenant_id == PayrollResultLine.tenant_id,
                        PayrollResultImport.id
                        == PayrollResultLine.payroll_result_import_id,
                    ),
                )
                .where(
                    PayrollResultLine.tenant_id == tenant_id,
                    PayrollResultLine.time_entry_id.in_(time_entry_ids),
                )
            )
        ).tuples().all()
    )


async def floor_check_time(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    period_start: date,
    period_end: date,
    contract_code: str | None,
) -> list[
    tuple[
        TimeEntry,
        Employee,
        FederalChargeCode,
        PayrollResultLine | None,
        FederalInvoiceSupportLine | None,
    ]
]:
    statement = (
        select(
            TimeEntry,
            Employee,
            FederalChargeCode,
            PayrollResultLine,
            FederalInvoiceSupportLine,
        )
        .join(
            Employee,
            and_(
                Employee.tenant_id == TimeEntry.tenant_id,
                Employee.id == TimeEntry.employee_id,
            ),
        )
        .join(
            FederalChargeCode,
            and_(
                FederalChargeCode.tenant_id == TimeEntry.tenant_id,
                FederalChargeCode.id == TimeEntry.federal_charge_code_id,
            ),
        )
        .outerjoin(
            PayrollResultLine,
            and_(
                PayrollResultLine.tenant_id == TimeEntry.tenant_id,
                PayrollResultLine.time_entry_id == TimeEntry.id,
            ),
        )
        .outerjoin(
            FederalInvoiceSupportLine,
            and_(
                FederalInvoiceSupportLine.tenant_id == TimeEntry.tenant_id,
                FederalInvoiceSupportLine.time_entry_id == TimeEntry.id,
            ),
        )
        .where(
            TimeEntry.tenant_id == tenant_id,
            TimeEntry.work_date >= period_start,
            TimeEntry.work_date <= period_end,
            TimeEntry.status != TimeEntryStatus.CORRECTED,
        )
        .order_by(TimeEntry.work_date, Employee.employee_number, TimeEntry.start_at)
    )
    if contract_code is not None:
        statement = statement.where(FederalChargeCode.contract_code == contract_code)
    return list((await session.execute(statement)).tuples().all())


async def latest_support(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    contract_code: str,
    task_order: str | None,
    period_start: date,
    period_end: date,
) -> FederalInvoiceSupport | None:
    return await session.scalar(
        select(FederalInvoiceSupport)
        .where(
            FederalInvoiceSupport.tenant_id == tenant_id,
            FederalInvoiceSupport.contract_code == contract_code,
            FederalInvoiceSupport.task_order.is_(task_order)
            if task_order is None
            else FederalInvoiceSupport.task_order == task_order,
            FederalInvoiceSupport.invoice_period_start == period_start,
            FederalInvoiceSupport.invoice_period_end == period_end,
        )
        .order_by(FederalInvoiceSupport.artifact_version.desc())
        .limit(1)
    )


async def get_support(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    support_id: uuid.UUID,
) -> FederalInvoiceSupport | None:
    return await session.scalar(
        select(FederalInvoiceSupport).where(
            FederalInvoiceSupport.tenant_id == tenant_id,
            FederalInvoiceSupport.id == support_id,
        )
    )


async def list_supports(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[FederalInvoiceSupport]:
    return list(
        await session.scalars(
            select(FederalInvoiceSupport)
            .where(FederalInvoiceSupport.tenant_id == tenant_id)
            .order_by(
                FederalInvoiceSupport.invoice_period_end.desc(),
                FederalInvoiceSupport.contract_code,
                FederalInvoiceSupport.task_order,
                FederalInvoiceSupport.artifact_version.desc(),
            )
        )
    )


async def support_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    support_id: uuid.UUID,
) -> list[FederalInvoiceSupportLine]:
    return list(
        await session.scalars(
            select(FederalInvoiceSupportLine)
            .where(
                FederalInvoiceSupportLine.tenant_id == tenant_id,
                FederalInvoiceSupportLine.federal_invoice_support_id == support_id,
            )
            .order_by(
                FederalInvoiceSupportLine.work_date,
                FederalInvoiceSupportLine.employee_name,
            )
        )
    )
