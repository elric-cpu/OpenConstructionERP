import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../app/AuthContext";
import {
  useCreateAssignment,
  useScheduleEntries,
  useScheduleResources,
} from "../modules/scheduling/useScheduling";
import type { ScheduleAssignmentInput } from "../modules/scheduling/types";

function localDateTime(hoursFromNow: number) {
  const value = new Date(Date.now() + hoursFromNow * 60 * 60 * 1000);
  value.setMinutes(0, 0, 0);
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}

const defaults: ScheduleAssignmentInput = {
  project_id: "",
  employee_id: "",
  title: "",
  start_at: localDateTime(1),
  end_at: localDateTime(9),
  location: "",
  required_tools: "",
  assignment_role: "",
};

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "The schedule request failed.";
}

export function SchedulePage() {
  const auth = useAuth();
  const resources = useScheduleResources();
  const entries = useScheduleEntries();
  const createAssignment = useCreateAssignment();
  const form = useForm<ScheduleAssignmentInput>({ defaultValues: defaults });
  const error =
    resources.projects.error ??
    resources.employees.error ??
    entries.error ??
    createAssignment.error;
  const availableEmployees = resources.employees.data?.filter((employee) =>
    ["IDENTITY_CREATED", "ACTIVE"].includes(employee.status),
  );

  async function submit(input: ScheduleAssignmentInput) {
    await createAssignment.mutateAsync(input);
    form.reset({ ...defaults, project_id: input.project_id, employee_id: input.employee_id });
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div><p className="eyebrow">Benson Construction ERP</p><h1>Dispatch schedule</h1></div>
        <div className="header-actions">
          <Link className="quiet" to="/sales/new">Sales</Link>
          <Link className="quiet" to="/time">Time</Link>
          <Link className="quiet" to="/employees">Employees</Link>
          <button className="quiet" onClick={() => auth.logout()} type="button">Sign out</button>
        </div>
      </header>
      <p className="page-intro">Assign employees to project work and surface schedule conflicts before dispatch.</p>
      {error && <div className="alert" role="alert">{errorMessage(error)}</div>}
      <div className="schedule-layout">
        <form className="form-card" onSubmit={form.handleSubmit(submit)}>
          <h2>Schedule an employee</h2>
          <div className="field-grid">
            <label className="wide">Project<select required {...form.register("project_id")}>
              <option value="">Select a project</option>
              {resources.projects.data?.map((project) => <option key={project.id} value={project.id}>{project.project_number} · {project.name}</option>)}
            </select></label>
            <label className="wide">Employee<select required {...form.register("employee_id")}>
              <option value="">Select an employee</option>
              {availableEmployees?.map((employee) => <option key={employee.id} value={employee.id}>{employee.employee_number} · {employee.first_name} {employee.last_name}</option>)}
            </select></label>
            <label className="wide">Work activity<input required {...form.register("title")} /></label>
            <label>Starts<input required type="datetime-local" {...form.register("start_at")} /></label>
            <label>Ends<input required type="datetime-local" {...form.register("end_at")} /></label>
            <label className="wide">Site or location<input {...form.register("location")} /></label>
            <label>Assignment role<input {...form.register("assignment_role")} /></label>
            <label>Required tools<input {...form.register("required_tools")} /></label>
          </div>
          <button className="primary" disabled={createAssignment.isPending} type="submit">
            {createAssignment.isPending ? "Checking conflicts…" : "Assign to schedule"}
          </button>
        </form>
        <section className="form-card">
          <div className="card-heading"><h2>Next 14 days</h2><span>{entries.data?.length ?? 0}</span></div>
          {entries.isLoading && <p>Loading the schedule…</p>}
          {!entries.isLoading && entries.data?.length === 0 && <p>No scheduled work in this window.</p>}
          <ol className="schedule-list">
            {entries.data?.map((entry) => (
              <li key={`${entry.activity.id}-${entry.assignment?.id ?? "open"}`}>
                <time dateTime={entry.activity.start_at}>
                  {new Date(entry.activity.start_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
                </time>
                <strong>{entry.activity.title}</strong>
                <span>{entry.project_name} · {entry.employee_name ?? "Unassigned"}</span>
                {entry.activity.location && <span>{entry.activity.location}</span>}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}
