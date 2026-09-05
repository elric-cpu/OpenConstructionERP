import { type FormEvent, useState } from "react";
import { operationsApi } from "./api";
import type { Employee } from "./types";

const initialForm = {
  name: "",
  email: "",
  invite_delivery_email: "",
  start_date: "",
  work_location: "Burns, Oregon",
  role: "field",
  federal_contract_applicability: "unknown",
  workspace_unlicensed_confirmed: false,
};

export function NewHireForm({ credential, onCreated }: { credential: string; onCreated(employee: Employee): void }) {
  const [form, setForm] = useState(initialForm);
  const [status, setStatus] = useState<"" | "saving" | "error">("");
  const [error, setError] = useState("");
  const update = (field: keyof typeof form, value: string | boolean) =>
    setForm((current) => ({ ...current, [field]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("saving");
    setError("");
    try {
      const employee = await operationsApi<Employee>("/api/benson/v1/employees", credential, {
        method: "POST",
        body: JSON.stringify({ ...form, classification: "employee" }),
      });
      onCreated(employee);
      setForm(initialForm);
      setStatus("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "New hire could not be saved");
      setStatus("error");
    }
  };
  return (
    <form className="new-hire-form workspace-card" onSubmit={(event) => void submit(event)}>
      <div className="section-kicker">NEW HIRE</div>
      <h2>Create the employee record</h2>
      <p className="form-intro">Set the managed login separately from the address that can receive the invitation.</p>
      <div className="field-grid">
        <label>
          Full name
          <input required value={form.name} onChange={(event) => update("name", event.target.value)} />
        </label>
        <label>
          Workspace login
          <input
            required
            type="email"
            placeholder="name@bensonhomesolutions.com"
            value={form.email}
            onChange={(event) => update("email", event.target.value)}
          />
          <small>Identity only. No paid Google Workspace license.</small>
        </label>
        <label>
          Invite delivery email
          <input
            required
            type="email"
            placeholder="Reachable personal email"
            value={form.invite_delivery_email}
            onChange={(event) => update("invite_delivery_email", event.target.value)}
          />
        </label>
        <label>
          Start date
          <input
            required
            type="date"
            value={form.start_date}
            onChange={(event) => update("start_date", event.target.value)}
          />
        </label>
        <label>
          Work location
          <input
            required
            value={form.work_location}
            onChange={(event) => update("work_location", event.target.value)}
          />
        </label>
        <label>
          Portal role
          <select value={form.role} onChange={(event) => update("role", event.target.value)}>
            <option value="field">Field</option>
            <option value="office">Office</option>
            <option value="estimator_pm">Estimator / PM</option>
            <option value="accounting">Accounting</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        <label className="field-wide">
          Federal-contract applicability
          <select
            value={form.federal_contract_applicability}
            onChange={(event) => update("federal_contract_applicability", event.target.value)}
          >
            <option value="unknown">Needs qualified review</option>
            <option value="not_applicable">Not applicable</option>
            <option value="applicable">Applicable</option>
          </select>
        </label>
        <label className="license-confirm field-wide">
          <input
            required
            type="checkbox"
            checked={form.workspace_unlicensed_confirmed}
            onChange={(event) => update("workspace_unlicensed_confirmed", event.target.checked)}
          />
          <span>I confirmed this account is in the unlicensed onboarding OU and has no paid Workspace license.</span>
        </label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="primary" disabled={status === "saving"} type="submit">
        {status === "saving" ? "Saving…" : "Create new hire"}
      </button>
    </form>
  );
}
