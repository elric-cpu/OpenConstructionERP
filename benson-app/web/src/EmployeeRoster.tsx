import { CheckCircle2, Mail, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { operationsApi } from "./api";
import type { Employee } from "./types";

export function EmployeeRoster({
  credential,
  employees,
  onInvited,
  onReview,
}: {
  credential: string;
  employees: Employee[];
  onInvited(employeeId: string): void;
  onReview(employee: Employee): void;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const invite = async (employee: Employee) => {
    setBusy(employee.id);
    setError("");
    try {
      await operationsApi(`/api/benson/v1/employees/${employee.id}/invite`, credential, { method: "POST" });
      onInvited(employee.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Invitation could not be queued");
    } finally {
      setBusy("");
    }
  };
  return (
    <section className="employee-roster workspace-card">
      <div className="roster-heading">
        <div>
          <div className="section-kicker">EMPLOYEE ROSTER</div>
          <h2>Onboarding control</h2>
        </div>
        <span>{employees.length} records</span>
      </div>
      {error && <p className="form-error">{error}</p>}
      {employees.length === 0 ? (
        <div className="roster-empty">
          <UserRound />
          <p>No employee records yet.</p>
        </div>
      ) : (
        <div className="employee-list">
          {employees.map((employee) => (
            <article className="employee-row" key={employee.id}>
              <div className="employee-mark">{employee.name.slice(0, 1).toUpperCase()}</div>
              <div className="employee-identity">
                <strong>{employee.name}</strong>
                <span>{employee.email}</span>
                <small>
                  {employee.role.replace("_", " ")} · starts {employee.start_date}
                </small>
              </div>
              <div className="employee-policy">
                <span className="license-pill">
                  <ShieldCheck /> No paid license
                </span>
                <small>
                  <Mail /> {employee.invite_delivery_email || employee.email}
                </small>
              </div>
              <span className={`task-status status-${employee.status}`}>{employee.status.replace("_", " ")}</span>
              <div className="employee-actions">
                {employee.status === "draft" && (
                  <button disabled={busy === employee.id} onClick={() => void invite(employee)}>
                    {busy === employee.id ? "Queuing…" : "Send invite"}
                  </button>
                )}
                {employee.status !== "draft" && <CheckCircle2 aria-label="Invitation created" />}
                <button className="text-button" onClick={() => onReview(employee)}>
                  Review
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
