from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.federal_labor import repository
from app.modules.federal_labor.models import (
    EmployeeQualification,
    FederalChargeCode,
    FederalLaborRate,
)
from app.modules.federal_labor.schemas import (
    FederalInvoiceException,
    FederalInvoicePreview,
    FederalInvoiceSupportLinePreview,
    FederalInvoiceSupportRequest,
)
from app.modules.payroll.models import PayrollResultImport, PayrollResultLine
from app.modules.people.models import Employee
from app.modules.timekeeping.models import TimeEntry

MONEY = Decimal("0.01")
HOURS = Decimal("0.01")


async def prepare_invoice(
    session: AsyncSession,
    principal: Principal,
    request: FederalInvoiceSupportRequest,
) -> FederalInvoicePreview:
    time_rows = await repository.invoice_time(
        session,
        principal.tenant_id,
        request.contract_code,
        request.task_order,
        request.invoice_period_start,
        request.invoice_period_end,
    )
    rates = await repository.period_rates(
        session,
        principal.tenant_id,
        request.invoice_period_start,
        request.invoice_period_end,
    )
    qualifications = await repository.period_qualifications(
        session,
        principal.tenant_id,
        request.invoice_period_start,
        request.invoice_period_end,
    )
    payroll_rows = await repository.payroll_results_for_entries(
        session,
        principal.tenant_id,
        [entry.id for entry, _, _ in time_rows],
    )
    payroll = {line.time_entry_id: (line, result) for line, result in payroll_rows}
    lines: list[FederalInvoiceSupportLinePreview] = []
    exceptions: list[FederalInvoiceException] = []
    for entry, employee, charge_code in time_rows:
        line, line_exceptions = _prepare_line(
            entry,
            employee,
            charge_code,
            rates,
            qualifications,
            payroll.get(entry.id),
        )
        exceptions.extend(line_exceptions)
        if line is not None:
            lines.append(line)
    total_hours = sum((line.approved_hours for line in lines), Decimal("0")).quantize(
        HOURS
    )
    total_amount = sum(
        (line.extended_amount for line in lines), Decimal("0")
    ).quantize(MONEY)
    return FederalInvoicePreview(
        lines=lines,
        total_approved_hours=total_hours,
        total_extended_amount=total_amount,
        exceptions=exceptions,
        ready=bool(lines) and not any(item.blocking for item in exceptions),
    )


def _prepare_line(
    entry: TimeEntry,
    employee: Employee,
    charge_code: FederalChargeCode,
    rates: Iterable[FederalLaborRate],
    qualifications: Iterable[EmployeeQualification],
    payroll: tuple[PayrollResultLine, PayrollResultImport] | None,
) -> tuple[
    FederalInvoiceSupportLinePreview | None,
    list[FederalInvoiceException],
]:
    exceptions = _entry_exceptions(entry, charge_code)
    billable_hours = (
        entry.regular_hours + entry.overtime_hours + entry.double_time_hours
    ).quantize(HOURS)
    excluded_hours = (
        entry.leave_hours + entry.indirect_hours + entry.travel_hours
    ).quantize(HOURS)
    if excluded_hours:
        exceptions.append(
            FederalInvoiceException(
                code="NON_BILLABLE_CLASSIFICATION_EXCLUDED",
                message=(
                    f"{excluded_hours} travel, leave, or indirect hours are excluded "
                    "because this invoice-support format has no authorized bill rate "
                    "for those classifications"
                ),
                time_entry_id=entry.id,
                blocking=bool(entry.travel_hours),
            )
        )
    if billable_hours == 0:
        return None, exceptions
    labor_category = entry.labor_category or charge_code.labor_category
    if not labor_category:
        exceptions.append(
            FederalInvoiceException(
                code="MISSING_LABOR_CATEGORY",
                message="Approved direct time has no labor category",
                time_entry_id=entry.id,
            )
        )
        return None, exceptions
    rate = _effective_rate(
        rates,
        charge_code.id,
        labor_category,
        entry.work_date,
    )
    if rate is None:
        exceptions.append(
            FederalInvoiceException(
                code="MISSING_BILL_RATE",
                message=(
                    f"No effective bill rate exists for {labor_category} on "
                    f"{entry.work_date.isoformat()}"
                ),
                time_entry_id=entry.id,
            )
        )
        return None, exceptions
    if rate.currency != "USD":
        exceptions.append(
            FederalInvoiceException(
                code="UNSUPPORTED_CURRENCY",
                message=f"Invoice support cannot aggregate {rate.currency} with USD",
                time_entry_id=entry.id,
            )
        )
    qualification_status, qualification_snapshot, qualification_exception = (
        _qualification(
            qualifications,
            employee.id,
            charge_code.required_qualification_code,
            entry.work_date,
        )
    )
    if qualification_exception is not None:
        qualification_exception.time_entry_id = entry.id
        exceptions.append(qualification_exception)
    payroll_status, payroll_snapshot = _payroll_snapshot(payroll)
    extended_amount = (
        entry.regular_hours * rate.regular_bill_rate
        + entry.overtime_hours * rate.overtime_bill_rate
        + entry.double_time_hours * rate.double_time_bill_rate
    ).quantize(MONEY, rounding=ROUND_HALF_UP)
    return (
        FederalInvoiceSupportLinePreview(
            time_entry_id=entry.id,
            employee_id=employee.id,
            employee_name=f"{employee.first_name} {employee.last_name}",
            work_date=entry.work_date,
            federal_charge_code_id=charge_code.id,
            agency_code=charge_code.agency_code,
            contract_code=charge_code.contract_code,
            task_order=charge_code.task_order,
            clin=charge_code.clin,
            funding_line=charge_code.funding_line,
            labor_category=labor_category,
            approved_hours=billable_hours,
            regular_hours=entry.regular_hours,
            overtime_hours=entry.overtime_hours,
            double_time_hours=entry.double_time_hours,
            regular_bill_rate=rate.regular_bill_rate,
            overtime_bill_rate=rate.overtime_bill_rate,
            double_time_bill_rate=rate.double_time_bill_rate,
            extended_amount=extended_amount,
            qualification_status=qualification_status,
            qualification_snapshot=qualification_snapshot,
            payroll_reconciliation_status=payroll_status,
            payroll_reconciliation_snapshot=payroll_snapshot,
            time_approval_snapshot={
                "time_entry_id": str(entry.id),
                "time_entry_version": entry.version,
                "certified_at": _iso(entry.certified_at),
                "certified_by": _uuid(entry.certified_by),
                "approved_at": _iso(entry.approved_at),
                "approved_by": _uuid(entry.approved_by),
            },
            bill_rate_snapshot={
                "federal_labor_rate_id": str(rate.id),
                "version": rate.version,
                "effective_from": rate.effective_from.isoformat(),
                "effective_to": (
                    rate.effective_to.isoformat() if rate.effective_to else None
                ),
                "currency": rate.currency,
                "regular_bill_rate": str(rate.regular_bill_rate),
                "overtime_bill_rate": str(rate.overtime_bill_rate),
                "double_time_bill_rate": str(rate.double_time_bill_rate),
                "source_reference": rate.source_reference,
                "formula": (
                    "regular_hours * regular_bill_rate + overtime_hours * "
                    "overtime_bill_rate + double_time_hours * double_time_bill_rate"
                ),
            },
        ),
        exceptions,
    )


def _entry_exceptions(
    entry: TimeEntry,
    charge_code: FederalChargeCode,
) -> list[FederalInvoiceException]:
    exceptions: list[FederalInvoiceException] = []
    if entry.work_date < charge_code.active_from or (
        charge_code.active_to is not None and entry.work_date > charge_code.active_to
    ):
        exceptions.append(
            FederalInvoiceException(
                code="CHARGE_CODE_NOT_EFFECTIVE",
                message="Charge code was not effective on the work date",
                time_entry_id=entry.id,
            )
        )
    comparisons = {
        "charge code": (entry.charge_code, charge_code.code),
        "contract": (entry.contract_code, charge_code.contract_code),
        "task order": (entry.task_order, charge_code.task_order),
        "CLIN": (entry.clin, charge_code.clin),
        "funding line": (entry.funding_line, charge_code.funding_line),
    }
    mismatches = [
        label
        for label, (time_value, canonical_value) in comparisons.items()
        if time_value is not None and time_value != canonical_value
    ]
    if mismatches:
        exceptions.append(
            FederalInvoiceException(
                code="FEDERAL_SNAPSHOT_MISMATCH",
                message="Approved time differs from canonical " + ", ".join(mismatches),
                time_entry_id=entry.id,
            )
        )
    return exceptions


def _effective_rate(
    rates: Iterable[FederalLaborRate],
    charge_code_id: object,
    labor_category: str,
    work_date: date,
) -> FederalLaborRate | None:
    matches = [
        rate
        for rate in rates
        if rate.federal_charge_code_id == charge_code_id
        and rate.labor_category == labor_category
        and rate.effective_from <= work_date
        and (rate.effective_to is None or rate.effective_to >= work_date)
    ]
    return max(matches, key=lambda rate: rate.effective_from, default=None)


def _qualification(
    qualifications: Iterable[EmployeeQualification],
    employee_id: object,
    qualification_code: str | None,
    work_date: date,
) -> tuple[str, dict, FederalInvoiceException | None]:
    if qualification_code is None:
        return "NOT_REQUIRED", {"required": False}, None
    matches = [
        item
        for item in qualifications
        if item.employee_id == employee_id
        and item.qualification_code == qualification_code
        and item.effective_from <= work_date
        and (item.effective_to is None or item.effective_to >= work_date)
    ]
    qualification = max(matches, key=lambda item: item.effective_from, default=None)
    if qualification is None:
        return (
            "MISSING",
            {"required": True, "qualification_code": qualification_code},
            FederalInvoiceException(
                code="MISSING_QUALIFICATION",
                message=(
                    f"Employee lacks active qualification {qualification_code} "
                    f"on {work_date.isoformat()}"
                ),
            ),
        )
    return (
        "QUALIFIED",
        {
            "required": True,
            "employee_qualification_id": str(qualification.id),
            "version": qualification.version,
            "qualification_code": qualification.qualification_code,
            "effective_from": qualification.effective_from.isoformat(),
            "effective_to": (
                qualification.effective_to.isoformat()
                if qualification.effective_to
                else None
            ),
            "verified_at": _iso(qualification.verified_at),
            "verified_by": _uuid(qualification.verified_by),
        },
        None,
    )


def _payroll_snapshot(
    payroll: tuple[PayrollResultLine, PayrollResultImport] | None,
) -> tuple[str, dict]:
    if payroll is None:
        return "NOT_IMPORTED", {"paid": False}
    line, result_import = payroll
    return (
        result_import.status.value,
        {
            "paid": True,
            "payroll_result_import_id": str(result_import.id),
            "payroll_result_line_id": str(line.id),
            "result_import_status": result_import.status.value,
            "pay_date": line.pay_date.isoformat(),
            "provider_payroll_id": line.provider_payroll_id,
            "payment_reference": line.payment_reference,
            "line_version": line.version,
        },
    )


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _uuid(value: object) -> str | None:
    return str(value) if value is not None else None
