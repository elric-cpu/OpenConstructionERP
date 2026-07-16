import { useMemo, useState } from "react";
import { ScheduleForm, type ScheduleDraft } from "./ScheduleForm";
import type { ScheduleEntry } from "./types";
import { useScheduleWorkspace } from "./useScheduleWorkspace";

const dayFormat = new Intl.DateTimeFormat("en-US", {
  dateStyle: "full",
  timeZone: "America/Los_Angeles",
});
const timeFormat = new Intl.DateTimeFormat("en-US", {
  timeStyle: "short",
  timeZone: "America/Los_Angeles",
});

function dayKey(iso: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(iso));
}

export function ScheduleWorkspace({ credential, email, role }: { credential: string; email: string; role: string }) {
  const canPlan = ["owner", "admin", "office", "estimator_pm"].includes(role);
  const canDeliver = ["owner", "admin", "office", "estimator_pm", "field"].includes(role);
  const { entries, jobs, save, staff, status, transition } = useScheduleWorkspace(credential, canPlan);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ScheduleEntry | null>(null);
  const groups = useMemo(() => {
    const sorted = [...entries].sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    return Object.entries(
      sorted.reduce<Record<string, ScheduleEntry[]>>((days, entry) => {
        (days[dayKey(entry.starts_at)] ||= []).push(entry);
        return days;
      }, {}),
    );
  }, [entries]);
  const closeForm = () => {
    setCreating(false);
    setEditing(null);
  };
  const submit = async (draft: ScheduleDraft) => {
    if (await save(draft, editing || undefined)) closeForm();
  };
  if (creating || editing) {
    return (
      <section className="schedule-workspace" aria-label="Schedule editor">
        {status && (
          <p className="form-status" role="status">
            {status}
          </p>
        )}
        <ScheduleForm entry={editing || undefined} jobs={jobs} staff={staff} onCancel={closeForm} onSave={submit} />
      </section>
    );
  }
  return (
    <section className="schedule-workspace" aria-labelledby="schedule-heading">
      <div className="headline schedule-headline">
        <div>
          <p>FIELD COORDINATION</p>
          <h1 id="schedule-heading">Schedule</h1>
          <span>Committed visits and work, shown in Pacific time.</span>
        </div>
        {canPlan && (
          <button className="primary" disabled={!jobs.length} onClick={() => setCreating(true)}>
            + Schedule work
          </button>
        )}
      </div>
      {status && (
        <p className="form-status" role="status">
          {status}
        </p>
      )}
      {!groups.length && !status && (
        <div className="empty">
          <h2>No scheduled work</h2>
          <p>
            {canPlan
              ? jobs.length
                ? "Create a schedule entry from an existing job."
                : "No planned or active jobs are available to schedule."
              : "No work is assigned to you."}
          </p>
        </div>
      )}
      <div className="schedule-days">
        {groups.map(([day, dayEntries]) => (
          <section key={day} aria-labelledby={`day-${day}`}>
            <h2 id={`day-${day}`}>{dayFormat.format(new Date(dayEntries[0].starts_at))}</h2>
            <div className="schedule-list">
              {dayEntries.map((entry) => (
                <article key={entry.id}>
                  <time dateTime={entry.starts_at}>
                    {timeFormat.format(new Date(entry.starts_at))}
                    <small>to {timeFormat.format(new Date(entry.ends_at))}</small>
                  </time>
                  <div>
                    <small>
                      {entry.job_number} · {entry.event_type.replace("_", " ")}
                    </small>
                    <h3>{entry.job_title}</h3>
                    <p>{entry.customer_name}</p>
                    {entry.site_address && <p>{entry.site_address}</p>}
                    <span>Assigned to {entry.assigned_to}</span>
                  </div>
                  <span className={`schedule-status ${entry.status}`}>{entry.status.replace("_", " ")}</span>
                  <div className="row-actions">
                    {canPlan && entry.status === "scheduled" && <button onClick={() => setEditing(entry)}>Edit</button>}
                    {canPlan && !["completed", "cancelled"].includes(entry.status) && (
                      <button className="danger-link" onClick={() => transition(entry, "cancelled")}>
                        Cancel visit
                      </button>
                    )}
                    {canDeliver && entry.assigned_to === email && entry.status === "scheduled" && (
                      <button onClick={() => transition(entry, "in_progress")}>Start visit</button>
                    )}
                    {canDeliver && entry.assigned_to === email && entry.status === "in_progress" && (
                      <button onClick={() => transition(entry, "completed")}>Complete visit</button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
