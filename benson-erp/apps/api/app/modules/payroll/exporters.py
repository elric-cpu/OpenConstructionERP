import csv
import io
import json
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape

from app.modules.payroll.models import PayrollExportFormat

EXPORT_COLUMNS = (
    "employee_id",
    "employee_name",
    "provider_employee_id",
    "work_date",
    "period_start",
    "period_end",
    "pay_date",
    "regular_hours",
    "regular_earning_code",
    "overtime_hours",
    "overtime_earning_code",
    "double_time_hours",
    "double_time_earning_code",
    "travel_hours",
    "travel_earning_code",
    "leave_hours",
    "leave_earning_code",
    "indirect_hours",
    "indirect_earning_code",
    "project_code",
    "cost_code",
    "charge_code",
    "labor_category",
    "work_classification",
    "wage_determination",
    "contract_code",
    "task_order",
    "clin",
    "funding_line",
    "base_rate",
    "overtime_rate",
    "double_time_rate",
    "fringe_rate",
    "cash_in_lieu_rate",
    "gross_labor",
    "job_cost_amount",
)


def render_export(
    rows: Sequence[dict[str, Any]],
    export_format: PayrollExportFormat,
) -> tuple[bytes, str, str]:
    if export_format is PayrollExportFormat.CSV:
        return _csv(rows), "text/csv; charset=utf-8", "csv"
    if export_format is PayrollExportFormat.JSON:
        return _json(rows), "application/json", "json"
    if export_format is PayrollExportFormat.XLSX:
        return (
            _xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    raise ValueError(f"Unsupported payroll export format {export_format}")


def _csv(rows: Sequence[dict[str, Any]]) -> bytes:
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _safe_csv(_scalar(row.get(column))) for column in EXPORT_COLUMNS})
    return target.getvalue().encode("utf-8")


def _json(rows: Sequence[dict[str, Any]]) -> bytes:
    payload = [
        {column: _scalar(row.get(column)) for column in EXPORT_COLUMNS}
        for row in rows
    ]
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _xlsx(rows: Sequence[dict[str, Any]]) -> bytes:
    output = io.BytesIO()
    sheet_rows = [_xlsx_row(EXPORT_COLUMNS, 1)]
    sheet_rows.extend(
        _xlsx_row(tuple(row.get(column) for column in EXPORT_COLUMNS), index)
        for index, row in enumerate(rows, start=2)
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Payroll Export" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def _xlsx_row(values: tuple[Any, ...], row_number: int) -> str:
    cells = []
    for index, value in enumerate(values, start=1):
        reference = f"{_column_name(index)}{row_number}"
        if isinstance(value, (int, float, Decimal)):
            cells.append(f'<c r="{reference}"><v>{escape(str(value))}</v></c>')
        else:
            rendered = escape(str(_scalar(value) or ""))
            cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{rendered}</t></is></c>')
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    return str(value)


def _safe_csv(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value
