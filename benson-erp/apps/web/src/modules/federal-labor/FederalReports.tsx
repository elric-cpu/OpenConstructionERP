import { useForm } from "react-hook-form";

import type {
  FederalChargeCode,
  FederalInvoicePreview,
  FederalInvoiceRequest,
  FederalInvoiceSupport,
  FloorCheckReport,
} from "./types";

function monthRange() {
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth(), 1);
  return {
    period_start: start.toISOString().slice(0, 10),
    period_end: end.toISOString().slice(0, 10),
  };
}

export type FloorCheckFilters = {
  period_start: string;
  period_end: string;
  contract_code: string;
};

export function FloorCheckPanel({
  filters,
  report,
  loading,
  onFilters,
}: {
  filters: FloorCheckFilters;
  report: FloorCheckReport | undefined;
  loading: boolean;
  onFilters: (filters: FloorCheckFilters) => void;
}) {
  const form = useForm<FloorCheckFilters>({ defaultValues: filters });
  return (
    <section className="form-card federal-report">
      <div className="card-heading">
        <div><p className="eyebrow">DCAA-ready inquiry</p><h2>Floor-check report</h2></div>
        <span>{report?.entries.length ?? 0} entries</span>
      </div>
      <form className="report-filter" onSubmit={form.handleSubmit(onFilters)}>
        <label>From<input required type="date" {...form.register("period_start")} /></label>
        <label>Through<input required type="date" {...form.register("period_end")} /></label>
        <label>Contract<input placeholder="All contracts" {...form.register("contract_code")} /></label>
        <button className="quiet" disabled={loading} type="submit">{loading ? "Checking…" : "Run report"}</button>
      </form>
      {report?.entries.length === 0 && <p>No approved federal labor matched this period.</p>}
      {(report?.entries.length ?? 0) > 0 && (
        <div className="table-scroll">
          <table className="federal-table">
            <thead><tr><th>Employee / date</th><th>Work performed</th><th>Contract allocation</th><th>Approvals</th><th>Disposition</th></tr></thead>
            <tbody>{report?.entries.map((entry) => (
              <tr key={`${entry.employee_id}-${entry.work_date}-${entry.contract_code}-${entry.description}`}>
                <td><strong>{entry.employee_name}</strong><small>{entry.work_date} · {entry.approved_hours}h</small></td>
                <td>{entry.description}<small>{entry.location || "Location not recorded"}</small></td>
                <td>{entry.contract_code}<small>{[entry.task_order, entry.clin, entry.labor_category].filter(Boolean).join(" · ")}</small></td>
                <td><span className="status-pill ready">Certified</span><small>{new Date(entry.approved_at).toLocaleString()}</small></td>
                <td>{entry.payroll_status}<small>Invoice: {entry.invoice_status}</small></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function FederalInvoicePanel({
  codes,
  preview,
  previewRequest,
  artifact,
  pending,
  onPreview,
  onGenerate,
}: {
  codes: FederalChargeCode[];
  preview: FederalInvoicePreview | undefined;
  previewRequest: FederalInvoiceRequest | undefined;
  artifact: FederalInvoiceSupport | undefined;
  pending: boolean;
  onPreview: (input: FederalInvoiceRequest) => Promise<unknown>;
  onGenerate: (input: FederalInvoiceRequest) => Promise<unknown>;
}) {
  const range = monthRange();
  const form = useForm<FederalInvoiceRequest>({
    defaultValues: {
      contract_code: "",
      task_order: null,
      invoice_number: null,
      invoice_period_start: range.period_start,
      invoice_period_end: range.period_end,
    },
  });
  return (
    <section className="form-card federal-report">
      <div className="card-heading">
        <div><p className="eyebrow">Immutable labor support</p><h2>Federal invoice support</h2></div>
        {preview && <span className={`status-pill ${preview.ready ? "ready" : ""}`}>{preview.ready ? "READY" : "EXCEPTIONS"}</span>}
      </div>
      <form className="report-filter" onSubmit={form.handleSubmit(onPreview)}>
        <label>Contract<select required {...form.register("contract_code")}>
          <option value="">Select contract</option>
          {[...new Set(codes.map((code) => code.contract_code))].map((contract) => <option key={contract}>{contract}</option>)}
        </select></label>
        <label>Task order<input {...form.register("task_order")} /></label>
        <label>Invoice number<input {...form.register("invoice_number")} /></label>
        <label>From<input required type="date" {...form.register("invoice_period_start")} /></label>
        <label>Through<input required type="date" {...form.register("invoice_period_end")} /></label>
        <button className="quiet" disabled={pending} type="submit">Preview support</button>
      </form>
      {preview && (
        <>
          <div className="federal-totals">
            <div><span>Approved labor</span><strong>{preview.total_approved_hours} hours</strong></div>
            <div><span>Extended billing</span><strong>${Number(preview.total_extended_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}</strong></div>
            <div><span>Source records</span><strong>{preview.lines.length}</strong></div>
          </div>
          {preview.exceptions.length > 0 && <ul className="exception-list">{preview.exceptions.map((item, index) => <li key={`${item.code}-${item.time_entry_id}-${index}`}><strong>{item.code}</strong><span>{item.message}</span>{item.time_entry_id && <small>Time entry {item.time_entry_id}</small>}</li>)}</ul>}
          {preview.lines.length > 0 && <InvoiceLines preview={preview} />}
          <button className="primary" disabled={!preview.ready || pending || !previewRequest} onClick={() => previewRequest && onGenerate(previewRequest)} type="button">
            {pending ? "Finalizing…" : "Generate immutable support"}
          </button>
        </>
      )}
      {artifact && <div className="artifact-proof"><strong>Artifact v{artifact.artifact_version} generated</strong><span>Checksum {artifact.content_checksum}</span><small>{artifact.lines.length} source-linked labor lines retained.</small></div>}
    </section>
  );
}

function InvoiceLines({ preview }: { preview: FederalInvoicePreview }) {
  return (
    <div className="table-scroll">
      <table className="federal-table">
        <thead><tr><th>Employee / date</th><th>Contract</th><th>Labor</th><th>Qualification</th><th>Payroll</th><th>Amount</th></tr></thead>
        <tbody>{preview.lines.map((line) => (
          <tr key={line.time_entry_id}>
            <td><strong>{line.employee_name}</strong><small>{line.work_date}</small></td>
            <td>{line.contract_code}<small>{[line.task_order, line.clin, line.funding_line].filter(Boolean).join(" · ")}</small></td>
            <td>{line.labor_category}<small>{line.approved_hours} approved hours</small></td>
            <td>{line.qualification_status}</td>
            <td>{line.payroll_reconciliation_status}</td>
            <td><strong>${Number(line.extended_amount).toFixed(2)}</strong><small>Source {line.time_entry_id.slice(0, 8)}</small></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
