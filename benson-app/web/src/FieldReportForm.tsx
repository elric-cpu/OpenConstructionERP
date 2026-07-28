import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { FieldReport, Job } from "./types";

export type FieldReportDraft = Pick<
  FieldReport,
  | "workforce_total"
  | "workforce_hours"
  | "weather"
  | "completed_work"
  | "materials"
  | "equipment"
  | "delays"
  | "issues"
  | "safety_observations"
> & { job_id: string; service_date: string };

export const emptyFieldReportDraft: FieldReportDraft = {
  job_id: "",
  service_date: new Date().toISOString().slice(0, 10),
  workforce_total: 0,
  workforce_hours: "",
  weather: "",
  completed_work: "",
  materials: "",
  equipment: "",
  delays: "",
  issues: "",
  safety_observations: [],
};

export function FieldReportForm({
  canCancel,
  draft,
  editing,
  jobs,
  onCancel,
  onSave,
  setDraft,
  status,
}: {
  canCancel: boolean;
  draft: FieldReportDraft;
  editing: boolean;
  jobs: Job[];
  onCancel(): void;
  onSave(): void;
  setDraft: Dispatch<SetStateAction<FieldReportDraft>>;
  status: string;
}) {
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSave();
  };
  return (
    <section className="schedule-workspace" aria-labelledby="field-editor-heading">
      <div className="headline">
        <div>
          <p>DAILY RECORD</p>
          <h1 id="field-editor-heading">Field report</h1>
        </div>
      </div>
      {status && (
        <p role="status" className="form-status">
          {status}
        </p>
      )}
      <form className="customer-form" onSubmit={submit}>
        <label>
          Job
          <select
            value={draft.job_id}
            disabled={editing}
            onChange={(event) => setDraft({ ...draft, job_id: event.target.value })}
            required
          >
            <option value="">Choose a job</option>
            {jobs.map((job) => (
              <option value={job.id} key={job.id}>
                {job.number} · {job.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Service date
          <input
            type="date"
            value={draft.service_date}
            disabled={editing}
            onChange={(event) => setDraft({ ...draft, service_date: event.target.value })}
            required
          />
        </label>
        <label>
          Workforce total
          <input
            type="number"
            min="0"
            value={draft.workforce_total}
            onChange={(event) => setDraft({ ...draft, workforce_total: Number(event.target.value) })}
          />
        </label>
        <label>
          Workforce hours <small>Operational record only; not certified payroll.</small>
          <input
            value={draft.workforce_hours}
            onChange={(event) => setDraft({ ...draft, workforce_hours: event.target.value })}
          />
        </label>
        {(["weather", "completed_work", "materials", "equipment", "delays", "issues"] as const).map((field) => (
          <label key={field}>
            {field.replace("_", " ")}
            <textarea
              value={draft[field]}
              onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
              required={field === "completed_work"}
            />
          </label>
        ))}
        <label>
          Safety observations <small>Observations only; use the formal incident process when required.</small>
          <textarea
            value={draft.safety_observations.join("\n")}
            onChange={(event) =>
              setDraft({ ...draft, safety_observations: event.target.value.split("\n").filter(Boolean) })
            }
          />
        </label>
        <div className="form-actions">
          <button type="submit" className="primary">
            Save draft
          </button>
          {canCancel && (
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
