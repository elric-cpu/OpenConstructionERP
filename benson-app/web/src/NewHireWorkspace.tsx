import { useEffect, useState } from "react";
import { EmployeeReviewPanel } from "./EmployeeReviewPanel";
import { EmployeeRoster } from "./EmployeeRoster";
import { NewHireForm } from "./NewHireForm";
import { onboardingApi } from "./onboardingApi";
import type { OnboardingEmployee } from "./onboardingTypes";

export function NewHireWorkspace({ credential }: { credential: string }) {
  const [employees, setEmployees] = useState<OnboardingEmployee[]>([]);
  const [selected, setSelected] = useState<OnboardingEmployee | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    onboardingApi.listEmployees(credential)
      .then((records) => active && setEmployees(records))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "Employees unavailable"));
    return () => {
      active = false;
    };
  }, [credential]);
  const refreshEmployees = async () => {
    const records = await onboardingApi.listEmployees(credential);
    setEmployees(records);
    setSelected((current) => records.find((record) => record.id === current?.id) ?? null);
  };
  if (selected) {
    return <EmployeeReviewPanel credential={credential} employee={selected} onBack={() => setSelected(null)} onEmployeeChanged={refreshEmployees} />;
  }
  return (
    <section className="new-hire-workspace">
      <div className="headline people-headline">
        <div>
          <p>PEOPLE OPERATIONS</p>
          <h1>New hires</h1>
          <span>Create the identity boundary, send the invitation, and review every required task.</span>
        </div>
        <div className="license-rule">
          <b>ZERO PAID LICENSES</b>
          <small>Workspace identity only</small>
        </div>
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="people-grid">
        <NewHireForm
          credential={credential}
          onCreated={(employee) =>
            setEmployees((current) => [...current, employee].sort((a, b) => a.name.localeCompare(b.name)))
          }
        />
        <EmployeeRoster credential={credential} employees={employees} onReview={setSelected} />
      </div>
    </section>
  );
}
