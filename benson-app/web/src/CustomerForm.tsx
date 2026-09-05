import { useEffect, useState } from "react";
import type { Customer } from "./types";

export type CustomerDraft = Omit<Customer, "id" | "status" | "source_lead_id" | "created_at" | "updated_at">;

const emptyDraft: CustomerDraft = {
  name: "",
  company: "",
  phone: "",
  email: null,
  billing_address: "",
  service_address: "",
  city: "",
  state: "OR",
  zip_code: "",
  notes: "",
};

export function CustomerForm({
  busy,
  customer,
  onCancel,
  onSave,
}: {
  busy: boolean;
  customer: Customer | null;
  onCancel(): void;
  onSave(draft: CustomerDraft): void;
}) {
  const [draft, setDraft] = useState<CustomerDraft>(emptyDraft);
  useEffect(() => {
    setDraft(customer ? { ...customer, email: customer.email || null } : emptyDraft);
  }, [customer]);
  const field = (key: keyof CustomerDraft, label: string, required = false) => (
    <label>
      {label}
      <input
        required={required}
        value={draft[key] ?? ""}
        onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
      />
    </label>
  );
  return (
    <form
      className="customer-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(draft);
      }}
    >
      <h2>{customer ? "Edit customer" : "Add customer"}</h2>
      <div className="form-grid">
        {field("name", "Customer name", true)}
        {field("company", "Company")}
        {field("phone", "Phone", true)}
        {field("email", "Email")}
        {field("service_address", "Service address")}
        {field("billing_address", "Billing address")}
        {field("city", "City")}
        {field("state", "State", true)}
        {field("zip_code", "ZIP code")}
      </div>
      <label>
        Notes
        <textarea
          value={draft.notes}
          onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
        />
      </label>
      <div className="form-actions">
        <button className="primary" disabled={busy} type="submit">
          {busy ? "Saving…" : "Save customer"}
        </button>
        <button disabled={busy} onClick={onCancel} type="button">
          Cancel
        </button>
      </div>
    </form>
  );
}
