import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../app/AuthContext";
import { EmployeeActivationPanel } from "../modules/people/EmployeeActivationPanel";
import {
  useApproveEmployee,
  useCreateEmployee,
  useEmployees,
  useProvisioning,
  useSelectedEmployeeStatus,
} from "../modules/people/useEmployeeOnboarding";
import type { Employee, EmployeeInput } from "../modules/people/types";

const defaults: EmployeeInput = {
  employee_number: "",
  first_name: "",
  last_name: "",
  personal_email: "",
  company_username: "",
  hire_date: new Date().toISOString().slice(0, 10),
};

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "The request could not be completed.";
}

export function EmployeesPage() {
  const auth = useAuth();
  const employees = useEmployees();
  const createEmployee = useCreateEmployee();
  const approveEmployee = useApproveEmployee();
  const [selected, setSelected] = useState<Employee | null>(null);
  const [reason, setReason] = useState("Manager reviewed and approved this new hire.");
  const selectedStatus = useSelectedEmployeeStatus(selected);
  const selectedEmployee =
    selectedStatus.data ??
    employees.data?.find((employee) => employee.id === selected?.id) ??
    selected;
  const provisioning = useProvisioning(selectedEmployee);
  const refetchEmployees = employees.refetch;
  const form = useForm<EmployeeInput>({ defaultValues: defaults });

  useEffect(() => {
    if (provisioning.data?.status === "CREATED") void refetchEmployees();
  }, [provisioning.data?.status, refetchEmployees]);

  async function create(input: EmployeeInput) {
    await createEmployee.mutateAsync(input);
    form.reset({ ...defaults, hire_date: input.hire_date });
  }

  async function approve(employee: Employee) {
    const result = await approveEmployee.mutateAsync({ employee, reason });
    setSelected(result.employee);
  }

  const error = createEmployee.error ?? approveEmployee.error ?? employees.error;
  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div><p className="eyebrow">Benson Construction ERP</p><h1>Employee onboarding</h1></div>
        <div className="header-actions">
          <Link className="quiet" to="/sales/new">Sales</Link>
          <Link className="quiet" to="/schedule">Schedule</Link>
          <Link className="quiet" to="/time">Time</Link>
          <Link className="quiet" to="/payroll">Payroll</Link>
          <Link className="quiet" to="/settings/security">Security</Link>
          <button className="quiet" onClick={() => auth.logout()} type="button">Sign out</button>
        </div>
      </header>
      <p className="page-intro">Approve a new hire and track creation of their unlicensed, company-managed Google identity.</p>
      {error && <div className="alert" role="alert">{message(error)}</div>}
      <div className="people-layout">
        <form className="form-card" onSubmit={form.handleSubmit(create)}>
          <h2>Add new hire</h2>
          <div className="field-grid">
            <label>Employee number<input required {...form.register("employee_number")} /></label>
            <label>Hire date<input required type="date" {...form.register("hire_date")} /></label>
            <label>First name<input required {...form.register("first_name")} /></label>
            <label>Last name<input required {...form.register("last_name")} /></label>
            <label className="wide">Personal email<input required type="email" {...form.register("personal_email")} /></label>
            <label className="wide">Company username<input required minLength={3} pattern="[a-z0-9][a-z0-9._-]{1,78}[a-z0-9]" {...form.register("company_username")} /></label>
          </div>
          <button className="primary" disabled={createEmployee.isPending} type="submit">
            {createEmployee.isPending ? "Saving…" : "Create employee draft"}
          </button>
        </form>
        <section className="form-card">
          <div className="card-heading"><h2>New hires</h2><span>{employees.data?.length ?? 0}</span></div>
          {employees.isLoading && <p>Loading employees…</p>}
          {!employees.isLoading && employees.data?.length === 0 && <p>No employee records yet.</p>}
          <ul className="employee-list">
            {employees.data?.map((employee) => (
              <EmployeeRow
                employee={employee}
                key={employee.id}
                onApprove={approve}
                onSelect={setSelected}
                pending={approveEmployee.isPending}
              />
            ))}
          </ul>
        </section>
      </div>
      {selectedEmployee && (
        <section className="form-card identity-card" aria-live="polite">
          <div><p className="eyebrow">Google identity</p><h2>{selectedEmployee.company_email ?? selectedEmployee.company_username}</h2></div>
          <label>Approval reason<input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <p>Status: <strong>{provisioning.data?.status ?? selectedEmployee.status.replaceAll("_", " ")}</strong></p>
          {provisioning.data?.external_user_id && <p>Directory user ID: {provisioning.data.external_user_id}</p>}
          <EmployeeActivationPanel employee={selectedEmployee} key={selectedEmployee.id} />
        </section>
      )}
    </main>
  );
}

function EmployeeRow({
  employee,
  onApprove,
  onSelect,
  pending,
}: {
  employee: Employee;
  onApprove: (employee: Employee) => Promise<void>;
  onSelect: (employee: Employee) => void;
  pending: boolean;
}) {
  return (
    <li>
      <button className="employee-summary" onClick={() => onSelect(employee)} type="button">
        <strong>{employee.first_name} {employee.last_name}</strong>
        <span>{employee.employee_number} · {employee.status.replaceAll("_", " ")}</span>
      </button>
      {employee.status === "DRAFT" && (
        <button className="primary" disabled={pending} onClick={() => onApprove(employee)} type="button">
          Approve
        </button>
      )}
    </li>
  );
}
