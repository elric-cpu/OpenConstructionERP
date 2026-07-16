import type { Dispatch, SetStateAction } from "react";
import { FileText, Save } from "lucide-react";
import { stringValue } from "./formatters";
import type { EditableLead, LeadDetail } from "./types";

export function LeadDetailsPanel({
  busy,
  edit,
  lead,
  save,
  setEdit,
}: {
  busy: boolean;
  edit: EditableLead;
  lead: LeadDetail;
  save(change: Record<string, string>): void;
  setEdit: Dispatch<SetStateAction<EditableLead>>;
}) {
  const intake = lead.payload;
  return (
    <section className="workspace-card intake-card">
      <div className="card-heading">
        <div>
          <small>REQUEST</small>
          <h2>Homeowner details</h2>
        </div>
        <FileText />
      </div>
      <form
        className="lead-edit-grid"
        onSubmit={(event) => {
          event.preventDefault();
          const { email, ...fields } = edit;
          save(email ? { ...fields, email } : fields);
        }}
      >
        <EditField label="Name" field="name" value={edit.name} setEdit={setEdit} />
        <EditField label="Phone" field="phone" value={edit.phone} setEdit={setEdit} />
        <EditField label="Email" field="email" type="email" value={edit.email} setEdit={setEdit} />
        <EditField label="Service" field="service_type" value={edit.service_type} setEdit={setEdit} />
        <EditField label="City" field="city" value={edit.city} setEdit={setEdit} />
        <EditField label="Lead source" field="source" value={edit.source} setEdit={setEdit} />
        <button className="secondary edit-save" disabled={busy}>
          <Save /> {busy ? "Saving…" : "Save lead details"}
        </button>
      </form>
      <dl className="intake-grid intake-message">
        <Detail label="Address" value={stringValue(intake.address)} />
        <Detail label="Timeline" value={stringValue(intake.timeline)} />
        <Detail label="Request" value={stringValue(intake.message)} wide />
        <Detail label="Access notes" value={stringValue(intake.access_notes)} wide />
      </dl>
    </section>
  );
}

function EditField({
  label,
  field,
  value,
  type = "text",
  setEdit,
}: {
  label: string;
  field: keyof EditableLead;
  value: string;
  type?: string;
  setEdit: Dispatch<SetStateAction<EditableLead>>;
}) {
  return (
    <label>
      {label}
      <input
        aria-label={label}
        type={type}
        required={field !== "email" && field !== "city"}
        value={value}
        onChange={(event) => setEdit((current) => ({ ...current, [field]: event.target.value }))}
      />
    </label>
  );
}

function Detail({ label, value, wide = false }: { label: string; value: string | null; wide?: boolean }) {
  return (
    <div className={wide ? "wide" : ""}>
      <dt>{label}</dt>
      <dd>{value || "Not provided"}</dd>
    </div>
  );
}
