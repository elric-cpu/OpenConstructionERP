import { useState } from "react";
import type { Customer, Estimate, EstimateLine } from "./types";

export type EstimateDraft = {
  customer_id: string;
  title: string;
  scope_notes: string;
  valid_until: string;
  lines: EstimateLine[];
};

const newLine = (): EstimateLine => ({ description: "", quantity: "1", unit: "each", unit_price_cents: 0 });

function initialDraft(customers: Customer[], estimate: Estimate | null): EstimateDraft {
  if (!estimate) {
    return { customer_id: customers[0]?.id || "", title: "", scope_notes: "", valid_until: "", lines: [newLine()] };
  }
  return {
    customer_id: estimate.customer_id,
    title: estimate.title,
    scope_notes: estimate.scope_notes,
    valid_until: estimate.valid_until,
    lines: estimate.lines.map(({ description, quantity, unit, unit_price_cents }) => ({
      description,
      quantity,
      unit,
      unit_price_cents,
    })),
  };
}

export function EstimateForm({
  busy,
  customers,
  estimate,
  onCancel,
  onSave,
}: {
  busy: boolean;
  customers: Customer[];
  estimate: Estimate | null;
  onCancel(): void;
  onSave(draft: EstimateDraft): void;
}) {
  const [draft, setDraft] = useState<EstimateDraft>(() => initialDraft(customers, estimate));
  const updateLine = (index: number, change: Partial<EstimateLine>) =>
    setDraft((current) => ({
      ...current,
      lines: current.lines.map((line, position) => (position === index ? { ...line, ...change } : line)),
    }));
  return (
    <form
      className="estimate-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(draft);
      }}
    >
      <h1>{estimate ? "Edit estimate" : "New estimate"}</h1>
      <div className="form-grid">
        <label>
          Customer
          <select
            disabled={Boolean(estimate)}
            required
            value={draft.customer_id}
            onChange={(event) => setDraft((current) => ({ ...current, customer_id: event.target.value }))}
          >
            <option value="">Select customer</option>
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estimate title
          <input
            required
            value={draft.title}
            onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
          />
        </label>
        <label>
          Valid until
          <input
            required
            type="date"
            value={draft.valid_until}
            onChange={(event) => setDraft((current) => ({ ...current, valid_until: event.target.value }))}
          />
        </label>
      </div>
      <label>
        Scope notes
        <textarea
          value={draft.scope_notes}
          onChange={(event) => setDraft((current) => ({ ...current, scope_notes: event.target.value }))}
        />
      </label>
      <h2>Line items</h2>
      <div className="estimate-lines">
        {draft.lines.map((line, index) => (
          <fieldset key={index}>
            <legend>Line {index + 1}</legend>
            <label>
              Description
              <input
                required
                value={line.description}
                onChange={(event) => updateLine(index, { description: event.target.value })}
              />
            </label>
            <label>
              Quantity
              <input
                min="0.01"
                required
                step="0.01"
                type="number"
                value={line.quantity}
                onChange={(event) => updateLine(index, { quantity: event.target.value })}
              />
            </label>
            <label>
              Unit
              <input required value={line.unit} onChange={(event) => updateLine(index, { unit: event.target.value })} />
            </label>
            <label>
              Unit price
              <input
                min="0"
                required
                step="0.01"
                type="number"
                value={(line.unit_price_cents / 100).toFixed(2)}
                onChange={(event) =>
                  updateLine(index, { unit_price_cents: Math.round(Number(event.target.value) * 100) })
                }
              />
            </label>
            {draft.lines.length > 1 && (
              <button
                type="button"
                onClick={() =>
                  setDraft((current) => ({
                    ...current,
                    lines: current.lines.filter((_, position) => position !== index),
                  }))
                }
              >
                Remove line
              </button>
            )}
          </fieldset>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setDraft((current) => ({ ...current, lines: [...current.lines, newLine()] }))}
      >
        + Add line
      </button>
      <div className="form-actions">
        <button className="primary" disabled={busy || !customers.length} type="submit">
          {busy ? "Saving…" : estimate ? "Save changes" : "Save draft"}
        </button>
        <button disabled={busy} type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
