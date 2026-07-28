import { CheckCircle2, Mail, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { operationsApi } from "./api";
import type { OnboardingEmployee } from "./onboardingTypes";

export function EmployeeRoster({
  credential,
  employees,
  onReview,
}: {
  credential: string;
  employees: OnboardingEmployee[];
  onReview(employee: OnboardingEmployee): void;
}) {
  const [deleting, setDeleting] = useState("");
  const [error, setError] = useState("");

  const deleteEmployee = async (employee: OnboardingEmployee) => {
    setDeleting(employee.id);
    setError("");
    try {
      await operationsApi(`/api/benson/v1/employees/${employee.id}`, credential, { method: "DELETE" });
      // Optionally, we could remove the employee from the list here, but we'll rely on a refetch or
      // the parent to update the list. For now, we just call the API and assume success.
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to delete employee");
    } finally {
      setDeleting("");
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
                  <>
                    <span className="license-pill">Identity setup required</span>
                    <button
                      className="text-button"
                      disabled={deleting === employee.id}
                      onClick={() => void deleteEmployee(employee)}
                    >
                      {deleting === employee.id ? "Deleting…" : "Delete"}
                    </button>
                  </>
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
