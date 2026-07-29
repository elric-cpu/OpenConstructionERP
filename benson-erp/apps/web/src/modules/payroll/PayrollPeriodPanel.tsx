import { useForm } from "react-hook-form";

import type { PayrollPeriod, PayrollPeriodInput } from "./types";

function defaults(): PayrollPeriodInput {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 13);
  const pay = new Date(end);
  pay.setDate(end.getDate() + 5);
  const iso = (value: Date) => value.toISOString().slice(0, 10);
  return {
    period_start: iso(start),
    period_end: iso(end),
    pay_date: iso(pay),
    workweek_definition: "Monday through Sunday",
    provider: "GENERIC",
  };
}

export function PayrollPeriodPanel({
  periods,
  selected,
  pending,
  onCreate,
  onSelect,
}: {
  periods: PayrollPeriod[];
  selected: PayrollPeriod | null;
  pending: boolean;
  onCreate: (input: PayrollPeriodInput) => Promise<unknown>;
  onSelect: (period: PayrollPeriod) => void;
}) {
  const form = useForm<PayrollPeriodInput>({ defaultValues: defaults() });
  return (
    <section className="payroll-sidebar">
      <form className="form-card" onSubmit={form.handleSubmit(onCreate)}>
        <h2>Open a payroll period</h2>
        <div className="field-grid">
          <label>Period start<input required type="date" {...form.register("period_start")} /></label>
          <label>Period end<input required type="date" {...form.register("period_end")} /></label>
          <label>Pay date<input required type="date" {...form.register("pay_date")} /></label>
          <label>Provider<select {...form.register("provider")}>
            {["GENERIC", "QUICKBOOKS_PAYROLL", "ADP", "GUSTO", "PAYCHEX", "RIPPLING", "UKG", "SAGE", "CONSTRUCTION_PAYROLL", "CUSTOM"].map((provider) => <option key={provider}>{provider}</option>)}
          </select></label>
          <label className="wide">Workweek definition<input required {...form.register("workweek_definition")} /></label>
        </div>
        <button className="primary" disabled={pending} type="submit">
          {pending ? "Creating…" : "Create payroll period"}
        </button>
      </form>
      <section className="form-card">
        <div className="card-heading"><h2>Payroll periods</h2><span>{periods.length}</span></div>
        {periods.length === 0 && <p>No payroll periods yet.</p>}
        <ol className="period-list">
          {periods.map((period) => (
            <li className={selected?.id === period.id ? "selected" : ""} key={period.id}>
              <button onClick={() => onSelect(period)} type="button">
                <strong>{period.period_start} – {period.period_end}</strong>
                <span>{period.provider.replaceAll("_", " ")} · {period.status.replaceAll("_", " ")}</span>
              </button>
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}
