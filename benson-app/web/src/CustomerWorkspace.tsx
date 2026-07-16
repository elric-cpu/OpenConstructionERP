import { useState } from "react";
import { requestHeaders } from "./api";
import { CustomerForm, type CustomerDraft } from "./CustomerForm";
import type { Customer, Lead } from "./types";

function isConvertibleLead(lead: Lead, customers: Customer[]) {
  return (
    ["qualified", "scheduled", "closed"].includes(lead.status) &&
    !lead.is_spam &&
    !customers.some((customer) => customer.source_lead_id === lead.id)
  );
}

export function CustomerWorkspace({
  canArchive,
  credential,
  customers,
  leads,
  setCustomers,
}: {
  canArchive: boolean;
  credential: string;
  customers: Customer[];
  leads: Lead[];
  setCustomers(value: Customer[] | ((current: Customer[]) => Customer[])): void;
}) {
  const [editing, setEditing] = useState<Customer | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [convertLead, setConvertLead] = useState("");
  const [status, setStatus] = useState("");
  const headers = { ...requestHeaders(credential), "content-type": "application/json" };
  const save = async (draft: CustomerDraft) => {
    setStatus("saving");
    const response = await fetch(editing ? `/api/benson/v1/customers/${editing.id}` : "/api/benson/v1/customers", {
      method: editing ? "PATCH" : "POST",
      headers,
      body: JSON.stringify(draft),
    });
    if (!response.ok) {
      setStatus("Unable to save customer.");
      return;
    }
    const saved = (await response.json()) as Customer;
    setCustomers((current) =>
      current.some((item) => item.id === saved.id)
        ? current.map((item) => (item.id === saved.id ? saved : item))
        : [...current, saved].sort((a, b) => a.name.localeCompare(b.name)),
    );
    setShowForm(false);
    setStatus("Customer saved.");
  };
  const convert = async () => {
    if (!convertLead) return;
    setStatus("saving");
    const response = await fetch(`/api/benson/v1/customers/from-lead/${convertLead}`, { method: "POST", headers });
    if (!response.ok) {
      setStatus(response.status === 409 ? "That lead is already a customer." : "Unable to convert lead.");
      return;
    }
    const saved = (await response.json()) as Customer;
    setCustomers((current) => [...current, saved].sort((a, b) => a.name.localeCompare(b.name)));
    setConvertLead("");
    setStatus("Lead converted to customer.");
  };
  const archive = async (customer: Customer) => {
    if (!window.confirm(`Archive ${customer.name}?`)) return;
    const response = await fetch(`/api/benson/v1/customers/${customer.id}`, { method: "DELETE", headers });
    if (response.ok) setCustomers((current) => current.filter((item) => item.id !== customer.id));
    setStatus(response.ok ? "Customer archived." : "Unable to archive customer.");
  };
  if (showForm) {
    return (
      <CustomerForm busy={status === "saving"} customer={editing} onCancel={() => setShowForm(false)} onSave={save} />
    );
  }
  return (
    <section className="customer-workspace" aria-labelledby="customers-heading">
      <div className="headline">
        <div>
          <p>CRM</p>
          <h1 id="customers-heading">Customers</h1>
          <span>Verified contacts and service locations.</span>
        </div>
        <button
          className="primary"
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
        >
          + Add customer
        </button>
      </div>
      <div className="conversion-bar">
        <label>
          Convert a lead
          <select
            aria-label="Lead to convert"
            value={convertLead}
            onChange={(event) => setConvertLead(event.target.value)}
          >
            <option value="">Select lead</option>
            {leads
              .filter((lead) => isConvertibleLead(lead, customers))
              .map((lead) => (
                <option key={lead.id} value={lead.id}>
                  {lead.name} — {lead.city}
                </option>
              ))}
          </select>
        </label>
        <button disabled={!convertLead || status === "saving"} onClick={convert}>
          Create customer
        </button>
      </div>
      {status && status !== "saving" && (
        <p className="form-status" role="status">
          {status}
        </p>
      )}
      <div className="customer-list">
        {customers.length === 0 && (
          <div className="empty">
            <h2>No customers yet</h2>
            <p>Add a verified contact or convert a qualified lead.</p>
          </div>
        )}
        {customers.map((customer) => (
          <article key={customer.id}>
            <div>
              <h2>{customer.name}</h2>
              <p>{customer.company || "Residential customer"}</p>
              <small>
                {[customer.service_address, customer.city, customer.state, customer.zip_code]
                  .filter(Boolean)
                  .join(", ") || "Service address not recorded"}
              </small>
            </div>
            <div className="customer-contact">
              <a href={`tel:${customer.phone}`}>{customer.phone}</a>
              {customer.email && <a href={`mailto:${customer.email}`}>{customer.email}</a>}
            </div>
            <div className="row-actions">
              <button
                onClick={() => {
                  setEditing(customer);
                  setShowForm(true);
                }}
              >
                Edit
              </button>
              {canArchive && (
                <button className="danger-link" onClick={() => archive(customer)}>
                  Archive
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
