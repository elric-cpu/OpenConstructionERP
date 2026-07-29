import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { PayrollReconciliationPanel } from "./PayrollReconciliationPanel";
import { PayrollReviewPanel } from "./PayrollReviewPanel";
import type {
  PayrollPeriod,
  PayrollPreview,
  PayrollReconciliation,
  PayrollResultImport,
} from "./types";

const period: PayrollPeriod = {
  id: "period-1",
  period_start: "2026-07-01",
  period_end: "2026-07-14",
  pay_date: "2026-07-18",
  status: "PAYROLL_REVIEW",
  workweek_definition: "Monday through Sunday",
  provider: "GENERIC",
  export_status: "NOT_STARTED",
  reconciliation_status: "NOT_STARTED",
  version: 4,
};

const preview: PayrollPreview = {
  payroll_period_id: period.id,
  provider: "GENERIC",
  approved_entry_count: 1,
  unapproved_entry_count: 1,
  employees: [],
  exceptions: [
    {
      code: "UNAPPROVED_TIME",
      message: "Time remains unapproved",
      time_entry_id: "entry-1",
      employee_id: "employee-1",
      internal_key: null,
    },
  ],
  totals: {
    employee_count: 1,
    regular_hours: "8.00",
    overtime_hours: "0.00",
    double_time_hours: "0.00",
    estimated_gross_labor: "200.00",
  },
  calculation: { gross_labor: "regular*base" },
  ready_to_lock: false,
};

test("blocks payroll locking while validation exceptions remain", () => {
  render(
    <PayrollReviewPanel
      exports={[]}
      onAdvance={vi.fn()}
      onDownload={vi.fn()}
      onGenerate={vi.fn()}
      onSensitive={vi.fn()}
      pending={false}
      period={period}
      preview={preview}
      sensitive={false}
    />,
  );
  expect(screen.getByRole("button", { name: "Lock payroll period" })).toBeDisabled();
  expect(screen.getByText("Time remains unapproved")).toBeVisible();
  expect(screen.getByText(/Source time entry: entry-1/)).toBeVisible();
});

test("requires reviewed resolutions before posting payroll job cost", () => {
  const resolve = vi.fn().mockResolvedValue(undefined);
  const result: PayrollResultImport = {
    id: "result-1",
    payroll_period_id: period.id,
    payroll_export_id: "export-1",
    provider: "GENERIC",
    provider_reference: "RUN-100",
    source_checksum: "a".repeat(64),
    imported_at: "2026-07-18T10:00:00Z",
    status: "EXCEPTIONS",
    reconciliation_summary: null,
    reconciled_at: null,
    version: 1,
  };
  const reconciliation: PayrollReconciliation = {
    result_import: result,
    exceptions: [
      {
        id: "exception-1",
        payroll_result_line_id: "line-1",
        code: "GROSS_WAGE_MISMATCH",
        message: "Gross does not match",
        expected_value: "200.00",
        actual_value: "201.00",
        status: "OPEN",
        version: 1,
      },
    ],
    job_cost_count: 0,
    job_cost_total: "0.00",
    calculation: { job_cost: "gross plus employer burden" },
  };
  render(
    <PayrollReconciliationPanel
      onReconcile={vi.fn()}
      onResolve={resolve}
      pending={false}
      reconciliation={reconciliation}
      result={result}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Reconcile and post project labor cost" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Record reviewed resolution" }));
  expect(resolve).toHaveBeenCalledWith(
    reconciliation.exceptions[0],
    expect.stringContaining("verified"),
  );
});
