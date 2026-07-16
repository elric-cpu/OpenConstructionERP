import { useState } from "react";
import type { Estimate, Job } from "./types";

export type JobPlan = {
  title?: string;
  target_start: string | null;
  target_completion: string | null;
  assigned_to: string | null;
  site_address: string;
};

export function JobPlanForm({
  estimate,
  job,
  onCancel,
  onSave,
}: {
  estimate?: Estimate;
  job?: Job;
  onCancel(): void;
  onSave(plan: JobPlan): void;
}) {
  const [title, setTitle] = useState(job?.title || estimate?.title || "");
  const [targetStart, setTargetStart] = useState(job?.target_start || "");
  const [targetCompletion, setTargetCompletion] = useState(job?.target_completion || "");
  const [assignedTo, setAssignedTo] = useState(job?.assigned_to || "");
  const [siteAddress, setSiteAddress] = useState(job?.site_address || "");
  return (
    <form
      className="job-plan-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({
          ...(job ? { title } : {}),
          target_start: targetStart || null,
          target_completion: targetCompletion || null,
          assigned_to: assignedTo || null,
          site_address: siteAddress,
        });
      }}
    >
      <div>
        <p>DELIVERY PLAN</p>
        <h1>{job ? `Edit ${job.number}` : `Create job from ${estimate?.number}`}</h1>
      </div>
      {job && (
        <label>
          Job title
          <input required value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
      )}
      <div className="job-plan-grid">
        <label>
          Target start
          <input type="date" value={targetStart} onChange={(event) => setTargetStart(event.target.value)} />
        </label>
        <label>
          Target completion
          <input
            type="date"
            min={targetStart}
            value={targetCompletion}
            onChange={(event) => setTargetCompletion(event.target.value)}
          />
        </label>
        <label>
          Assigned staff email
          <input type="email" value={assignedTo} onChange={(event) => setAssignedTo(event.target.value)} />
        </label>
      </div>
      <label>
        Site address
        <input value={siteAddress} onChange={(event) => setSiteAddress(event.target.value)} />
      </label>
      <div className="form-actions">
        <button className="primary" type="submit">
          {job ? "Save job plan" : "Create planned job"}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
