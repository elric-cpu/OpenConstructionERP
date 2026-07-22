import { useState } from "react";
import { JobPlanForm, type JobPlan } from "./JobPlanForm";
import type { Estimate, Job } from "./types";
import { useJobWorkspace } from "./useJobWorkspace";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function JobWorkspace({
  canCancel,
  canDeliver,
  canPlan,
  credential,
}: {
  canCancel: boolean;
  canDeliver: boolean;
  canPlan: boolean;
  credential: string;
}) {
  const { create, estimates, jobs, staff, status, transition, update } = useJobWorkspace(credential, canPlan);
  const [source, setSource] = useState<Estimate | null>(null);
  const [editing, setEditing] = useState<Job | null>(null);
  const closeForm = () => {
    setSource(null);
    setEditing(null);
  };
  const save = async (plan: JobPlan) => {
    const saved = editing ? await update(editing, plan) : source ? await create(source, plan) : false;
    if (saved) closeForm();
  };
  if (source || editing) {
    return (
      <JobPlanForm
        estimate={source || undefined}
        job={editing || undefined}
        onCancel={closeForm}
        onSave={save}
        staff={staff}
      />
    );
  }
  return (
    <section className="job-workspace" aria-labelledby="jobs-heading">
      <div className="headline">
        <div>
          <p>DELIVERY</p>
          <h1 id="jobs-heading">Jobs</h1>
          <span>Accepted scope converted into an attributable delivery record.</span>
        </div>
        {canPlan && (
          <button
            className="primary"
            disabled={!estimates.length}
            onClick={() => estimates[0] && setSource(estimates[0])}
            title={estimates.length ? "Create a job from an accepted estimate" : "Accept an estimate before creating a job"}
          >
            + New job
          </button>
        )}
      </div>
      {status && !["loading", "saving"].includes(status) && (
        <p className="form-status" role="status">
          {status}
        </p>
      )}
      {canPlan && estimates.length > 0 && (
        <section className="accepted-estimates" aria-labelledby="accepted-estimates-heading">
          <h2 id="accepted-estimates-heading">Accepted estimates ready for job setup</h2>
          {estimates.map((estimate) => (
            <article key={estimate.id}>
              <div>
                <small>{estimate.number}</small>
                <strong>{estimate.title}</strong>
                <span>{estimate.customer_name}</span>
              </div>
              <b>{money.format(estimate.total_cents / 100)}</b>
              <button className="primary" onClick={() => setSource(estimate)}>
                Create job
              </button>
            </article>
          ))}
        </section>
      )}
      <div className="job-list">
        {!jobs.length && status !== "loading" && (
          <div className="empty">
            <h2>No jobs yet</h2>
            <p>
              {canPlan
                ? "Accept an estimate, then use New job to create the planned delivery record."
                : "An office, estimator, or administrator can create a job from an accepted estimate."}
            </p>
          </div>
        )}
        {jobs.map((job) => (
          <article key={job.id}>
            <div>
              <small>
                {job.number} · {job.estimate_number}
              </small>
              <h2>{job.title}</h2>
              <p>
                {job.customer_name}
                {job.site_address ? ` · ${job.site_address}` : ""}
              </p>
              <p>
                {job.target_start || "Start not scheduled"} → {job.target_completion || "Completion not scheduled"}
              </p>
            </div>
            <strong>{money.format(job.contract_value_cents / 100)}</strong>
            <span className={`job-status ${job.status}`}>{job.status.replace("_", " ")}</span>
            <div className="row-actions">
              {canPlan && !["completed", "cancelled"].includes(job.status) && (
                <button onClick={() => setEditing(job)}>Edit plan</button>
              )}
              {canDeliver && job.status === "planned" && (
                <button onClick={() => transition(job, "active")}>Start job</button>
              )}
              {canDeliver && job.status === "on_hold" && (
                <button onClick={() => transition(job, "active")}>Resume job</button>
              )}
              {canDeliver && job.status === "active" && (
                <button onClick={() => transition(job, "completed")}>Complete job</button>
              )}
              {canDeliver && ["planned", "active"].includes(job.status) && (
                <button onClick={() => transition(job, "on_hold")}>Place on hold</button>
              )}
              {canCancel && !["completed", "cancelled"].includes(job.status) && (
                <button className="danger-link" onClick={() => transition(job, "cancelled")}>
                  Cancel job
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
