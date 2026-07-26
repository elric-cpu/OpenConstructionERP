import type { PayrollExport, PayrollPeriod, PayrollPeriodStatus, PayrollPreview } from "./types";

const nextStatus: Partial<Record<PayrollPeriodStatus, PayrollPeriodStatus>> = {
  OPEN: "EMPLOYEE_REVIEW",
  EMPLOYEE_REVIEW: "SUPERVISOR_REVIEW",
  SUPERVISOR_REVIEW: "PAYROLL_REVIEW",
  PAYROLL_REVIEW: "LOCKED",
};

export function PayrollReviewPanel({
  period,
  preview,
  exports,
  pending,
  sensitive,
  onSensitive,
  onAdvance,
  onGenerate,
  onDownload,
}: {
  period: PayrollPeriod;
  preview: PayrollPreview | undefined;
  exports: PayrollExport[];
  pending: boolean;
  sensitive: boolean;
  onSensitive: (checked: boolean) => void;
  onAdvance: (target: PayrollPeriodStatus) => Promise<unknown>;
  onGenerate: (format: PayrollExport["format"]) => Promise<unknown>;
  onDownload: (item: PayrollExport) => Promise<void>;
}) {
  const target = nextStatus[period.status];
  return (
    <section className="payroll-review">
      <section className="form-card">
        <div className="card-heading">
          <div><p className="eyebrow">{period.provider.replaceAll("_", " ")}</p><h2>{period.period_start} – {period.period_end}</h2></div>
          <span className={`status-badge ${preview?.ready_to_lock ? "ready" : ""}`}>{period.status.replaceAll("_", " ")}</span>
        </div>
        {!preview && <p>Loading payroll validation…</p>}
        {preview && <Totals preview={preview} />}
        {target && (
          <button
            className="primary"
            disabled={pending || (target === "LOCKED" && !preview?.ready_to_lock)}
            onClick={() => onAdvance(target)}
            type="button"
          >
            {target === "LOCKED" ? "Lock payroll period" : `Advance to ${target.replaceAll("_", " ").toLowerCase()}`}
          </button>
        )}
      </section>
      {preview && <Exceptions preview={preview} />}
      {preview && <EmployeeBreakdown preview={preview} />}
      {["LOCKED", "EXPORTED", "PROCESSED", "RECONCILED"].includes(period.status) && (
        <section className="form-card">
          <h2>Immutable export artifacts</h2>
          <label className="checkbox-label"><input checked={sensitive} onChange={(event) => onSensitive(event.target.checked)} type="checkbox" />Include authorized wage and job-cost fields</label>
          <div className="export-actions">
            {(["CSV", "XLSX", "JSON"] as const).map((format) => <button className="quiet" disabled={pending || exports.some((item) => item.format === format)} key={format} onClick={() => onGenerate(format)} type="button">Generate {format}</button>)}
          </div>
          <ol className="export-list">
            {exports.map((item) => <li key={item.id}><div><strong>{item.filename}</strong><span>SHA-256 {item.file_checksum.slice(0, 16)}… · v{item.artifact_version}</span></div><button className="quiet" onClick={() => onDownload(item)} type="button">Download</button></li>)}
          </ol>
        </section>
      )}
    </section>
  );
}

function Totals({ preview }: { preview: PayrollPreview }) {
  return <dl className="payroll-totals">{["employee_count", "regular_hours", "overtime_hours", "double_time_hours", "estimated_gross_labor"].map((key) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{preview.totals[key] ?? "Restricted"}</dd></div>)}</dl>;
}

function Exceptions({ preview }: { preview: PayrollPreview }) {
  return <section className="form-card"><div className="card-heading"><h2>Blocking exceptions</h2><span>{preview.exceptions.length}</span></div>{preview.exceptions.length === 0 ? <p className="ready-text">All required approvals, mappings, rates, and classifications are complete.</p> : <ol className="exception-list">{preview.exceptions.map((item, index) => <li key={`${item.code}-${item.time_entry_id ?? index}`}><strong>{item.code.replaceAll("_", " ")}</strong><span>{item.message}</span>{item.internal_key && <code>{item.internal_key}</code>}{item.time_entry_id && <small>Source time entry: {item.time_entry_id}</small>}</li>)}</ol>}</section>;
}

function EmployeeBreakdown({ preview }: { preview: PayrollPreview }) {
  return <section className="form-card"><h2>Employee source drill-down</h2><div className="table-scroll"><table><thead><tr><th>Employee</th><th>Regular</th><th>OT</th><th>Double</th><th>Travel</th><th>Gross</th><th>Sources</th></tr></thead><tbody>{preview.employees.map((employee) => <tr key={employee.employee_id}><th>{employee.employee_number}<span>{employee.employee_name}</span></th><td>{employee.regular_hours}</td><td>{employee.overtime_hours}</td><td>{employee.double_time_hours}</td><td>{employee.travel_hours}</td><td>{employee.estimated_gross_labor ?? "Restricted"}</td><td>{employee.source_time_entry_ids.map((id) => <code key={id}>{id.slice(0, 8)}</code>)}</td></tr>)}</tbody></table></div><p className="field-note">{preview.calculation.gross_labor}</p></section>;
}
