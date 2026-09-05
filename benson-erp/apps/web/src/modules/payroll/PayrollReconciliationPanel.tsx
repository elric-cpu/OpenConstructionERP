import { useState, type FormEvent } from "react";

import type {
  PayrollExport,
  PayrollPeriod,
  PayrollReconciliation,
  PayrollResultImport,
  PayrollResultLineInput,
  ReconciliationException,
} from "./types";

const example = JSON.stringify(
  [
    {
      time_entry_id: "source-time-entry-uuid",
      provider_employee_id: "provider-employee-id",
      work_date: "2026-07-23",
      pay_date: "2026-07-30",
      regular_hours: "8.00",
      overtime_hours: "0.00",
      double_time_hours: "0.00",
      base_rate: "25.0000",
      overtime_rate: "37.5000",
      double_time_rate: "50.0000",
      gross_wages: "200.00",
      employer_taxes: "18.00",
      employee_deductions: "20.00",
      employer_benefits: "10.00",
      workers_compensation: "4.00",
      fringe_benefits: "0.00",
      net_pay: "180.00",
    },
  ],
  null,
  2,
);

export function PayrollResultImportPanel({
  period,
  exports,
  pending,
  onImport,
}: {
  period: PayrollPeriod;
  exports: PayrollExport[];
  pending: boolean;
  onImport: (
    payrollExport: PayrollExport,
    providerReference: string,
    lines: PayrollResultLineInput[],
  ) => Promise<unknown>;
}) {
  const [exportId, setExportId] = useState(exports[0]?.id ?? "");
  const [reference, setReference] = useState("");
  const [payload, setPayload] = useState(example);
  const [localError, setLocalError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const lines = JSON.parse(payload) as PayrollResultLineInput[];
      if (!Array.isArray(lines) || lines.length === 0) throw new Error("At least one result row is required.");
      const payrollExport = exports.find((item) => item.id === exportId);
      if (!payrollExport) throw new Error("Select the immutable export returned by the provider.");
      setLocalError(null);
      await onImport(payrollExport, reference, lines);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "Invalid provider result JSON.");
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h2>Import provider payroll results</h2>
      <p className="field-note">Controlled JSON import links every paid row to its source time entry and export snapshot. Wage data requires payroll reconciliation permission.</p>
      {localError && <div className="alert" role="alert">{localError}</div>}
      <div className="field-grid">
        <label>Source export<select required value={exportId} onChange={(event) => setExportId(event.target.value)}>
          <option value="">Select export</option>
          {exports.map((item) => <option key={item.id} value={item.id}>{item.format} · {item.filename}</option>)}
        </select></label>
        <label>Provider payroll reference<input required value={reference} onChange={(event) => setReference(event.target.value)} /></label>
        <label className="wide">Provider result rows<textarea required rows={16} value={payload} onChange={(event) => setPayload(event.target.value)} /></label>
      </div>
      <button className="primary" disabled={pending} type="submit">{pending ? "Importing…" : `Import ${period.provider.replaceAll("_", " ")} results`}</button>
    </form>
  );
}

export function PayrollReconciliationPanel({
  result,
  reconciliation,
  pending,
  onResolve,
  onReconcile,
}: {
  result: PayrollResultImport;
  reconciliation: PayrollReconciliation | undefined;
  pending: boolean;
  onResolve: (item: ReconciliationException, reason: string) => Promise<unknown>;
  onReconcile: () => Promise<unknown>;
}) {
  const [reason, setReason] = useState("Payroll administrator verified this exception against the provider pay register.");
  const open = reconciliation?.exceptions.filter((item) => item.status === "OPEN") ?? [];
  return (
    <section className="form-card">
      <div className="card-heading"><div><p className="eyebrow">Provider results</p><h2>{result.provider_reference}</h2></div><span className={`status-badge ${result.status === "RECONCILED" ? "ready" : ""}`}>{result.status}</span></div>
      <p>Source SHA-256: <code>{result.source_checksum}</code></p>
      {!reconciliation && <p>Loading reconciliation…</p>}
      {reconciliation && (
        <>
          <dl className="payroll-totals">
            <div><dt>Open exceptions</dt><dd>{open.length}</dd></div>
            <div><dt>Job-cost rows</dt><dd>{reconciliation.job_cost_count}</dd></div>
            <div><dt>Job-cost total</dt><dd>{reconciliation.job_cost_total}</dd></div>
          </dl>
          {open.length > 0 && <label>Exception resolution reason<input minLength={10} value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
          <ol className="exception-list">
            {reconciliation.exceptions.map((item) => <li key={item.id}><strong>{item.code.replaceAll("_", " ")}</strong><span>{item.message}</span><small>Expected: {item.expected_value ?? "none"} · Actual: {item.actual_value ?? "none"}</small>{item.status === "OPEN" && <button className="quiet" disabled={pending || reason.length < 10} onClick={() => onResolve(item, reason)} type="button">Record reviewed resolution</button>}</li>)}
          </ol>
          {result.status !== "RECONCILED" && <button className="primary" disabled={pending || open.length > 0} onClick={onReconcile} type="button">Reconcile and post project labor cost</button>}
          <p className="field-note">{reconciliation.calculation.job_cost}</p>
        </>
      )}
    </section>
  );
}
