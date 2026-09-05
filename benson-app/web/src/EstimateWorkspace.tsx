import { useState } from "react";
import { EstimateForm, type EstimateDraft } from "./EstimateForm";
import type { Customer, Estimate } from "./types";
import { useEstimateWorkspace } from "./useEstimateWorkspace";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function EstimateWorkspace({
  canVoid,
  credential,
  customers,
}: {
  canVoid: boolean;
  credential: string;
  customers: Customer[];
}) {
  const { estimates, save, status, transition } = useEstimateWorkspace(credential);
  const [editing, setEditing] = useState<Estimate | null>(null);
  const [showForm, setShowForm] = useState(false);
  const closeForm = () => {
    setEditing(null);
    setShowForm(false);
  };
  const saveAndClose = async (draft: EstimateDraft) => {
    if (await save(draft, editing)) closeForm();
  };
  if (showForm) {
    return (
      <EstimateForm
        busy={status === "saving"}
        customers={customers}
        estimate={editing}
        onCancel={closeForm}
        onSave={saveAndClose}
      />
    );
  }
  return (
    <section className="estimate-workspace" aria-labelledby="estimates-heading">
      <div className="headline">
        <div>
          <p>SALES</p>
          <h1 id="estimates-heading">Estimates</h1>
          <span>Server-totaled scope and pricing linked to verified customers.</span>
        </div>
        <button
          className="primary"
          disabled={!customers.length}
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
        >
          + New estimate
        </button>
      </div>
      {!customers.length && <p className="form-status">Add a customer before creating an estimate.</p>}
      {status && !["loading", "saving"].includes(status) && (
        <p className="form-status" role="status">
          {status}
        </p>
      )}
      <div className="estimate-list">
        {!estimates.length && status !== "loading" && (
          <div className="empty">
            <h2>No estimates yet</h2>
            <p>Create a draft from a verified customer record.</p>
          </div>
        )}
        {estimates.map((estimate) => (
          <article key={estimate.id}>
            <div>
              <small>
                {estimate.number} · v{estimate.version}
              </small>
              <h2>{estimate.title}</h2>
              <p>
                {estimate.customer_name} · Valid through {estimate.valid_until}
              </p>
            </div>
            <strong>{money.format(estimate.total_cents / 100)}</strong>
            <span className={`estimate-status ${estimate.status}`}>{estimate.status}</span>
            <div className="row-actions">
              {estimate.status === "draft" && (
                <>
                  <button
                    onClick={() => {
                      setEditing(estimate);
                      setShowForm(true);
                    }}
                  >
                    Edit
                  </button>
                  <button onClick={() => transition(estimate, "ready")}>Mark ready</button>
                </>
              )}
              {estimate.status === "ready" && (
                <>
                  <button onClick={() => transition(estimate, "draft")}>Return to draft</button>
                  <button onClick={() => transition(estimate, "sent")}>Mark delivered</button>
                </>
              )}
              {estimate.status === "sent" && (
                <>
                  <button onClick={() => transition(estimate, "accepted")}>Record accepted</button>
                  <button onClick={() => transition(estimate, "declined")}>Record declined</button>
                </>
              )}
              {canVoid && ["draft", "ready", "sent"].includes(estimate.status) && (
                <button className="danger-link" onClick={() => transition(estimate, "void")}>
                  Void
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
