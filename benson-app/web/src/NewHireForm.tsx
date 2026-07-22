import { type FormEvent, useState } from "react";
import { onboardingApi } from "./onboardingApi";
import type { OnboardingEmployee } from "./onboardingTypes";

const initialForm = { name: "", email: "" };

function localDate(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export function NewHireForm({ credential, onCreated }: { credential: string; onCreated(employee: OnboardingEmployee): void }) {
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const employee = await onboardingApi.createEmployee(credential, {
          name: form.name,
          invite_delivery_email: form.email,
          start_date: localDate(),
          work_location: "Burns, Oregon",
          classification: "employee",
          role: "field",
          federal_contract_applicability: "unknown",
        email: form.email,
      });
      onCreated(employee);
      setForm(initialForm);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "New-hire onboarding could not be started");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="new-hire-form workspace-card" onSubmit={(event) => void submit(event)}>
      <div className="section-kicker">NEW HIRE</div>
      <h2>Start onboarding</h2>
      <p className="form-intro">
        Benson reserves the managed Workspace login and assigns the onboarding checklist. Credentials are sent only after Google setup is verified.
      </p>
      <div className="field-grid">
        <label>
          Full name
          <input
            required
            autoComplete="name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </label>
        <label>
          Email address
          <input
            required
            autoComplete="email"
            type="email"
            placeholder="Reachable personal email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </label>
      </div>
      <p className="form-intro">
        Federal-contract items are assigned for qualified applicability review; they are not treated as universally
        required.
      </p>
      {error && <p className="form-error">{error}</p>}
      <button className="primary" disabled={saving} type="submit">
        {saving ? "Starting onboarding…" : "Create onboarding record"}
      </button>
    </form>
  );
}
