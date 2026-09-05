import { useForm } from "react-hook-form";

import type { Employee } from "../people/types";
import type { Project } from "../scheduling/types";
import type { PayRateInput, PayrollMappingInput, PayrollPeriod } from "./types";

const today = new Date().toISOString().slice(0, 10);

export function PayrollSetupPanel({
  employees,
  projects,
  period,
  pending,
  onPayRate,
  onMapping,
}: {
  employees: Employee[];
  projects: Project[];
  period: PayrollPeriod;
  pending: boolean;
  onPayRate: (input: PayRateInput) => Promise<unknown>;
  onMapping: (input: PayrollMappingInput) => Promise<unknown>;
}) {
  const rate = useForm<PayRateInput>({
    defaultValues: {
      employee_id: "",
      effective_from: period.period_start,
      effective_to: null,
      base_rate: 25,
      overtime_rate: 37.5,
      double_time_rate: 50,
      fringe_rate: 0,
      cash_in_lieu_rate: 0,
    },
  });
  const mapping = useForm<PayrollMappingInput>({
    defaultValues: {
      provider: period.provider,
      mapping_type: "EMPLOYEE",
      internal_key: "",
      external_code: "",
      effective_from: period.period_start || today,
      effective_to: null,
      configuration: {},
    },
  });
  return (
    <section className="setup-grid">
      <form className="form-card" onSubmit={rate.handleSubmit(onPayRate)}>
        <h2>Date-effective pay rate</h2>
        <label>Employee<select required {...rate.register("employee_id")}>
          <option value="">Select employee</option>
          {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.employee_number} · {employee.first_name} {employee.last_name}</option>)}
        </select></label>
        <div className="field-grid">
          <label>Effective from<input required type="date" {...rate.register("effective_from")} /></label>
          <MoneyField label="Base rate" name="base_rate" form={rate} />
          <MoneyField label="Overtime rate" name="overtime_rate" form={rate} />
          <MoneyField label="Double-time rate" name="double_time_rate" form={rate} />
          <MoneyField label="Fringe rate" name="fringe_rate" form={rate} />
          <MoneyField label="Cash in lieu" name="cash_in_lieu_rate" form={rate} />
        </div>
        <button className="quiet" disabled={pending} type="submit">Save pay rate</button>
      </form>
      <form className="form-card" onSubmit={mapping.handleSubmit(onMapping)}>
        <h2>Provider mapping</h2>
        <div className="field-grid">
          <label>Mapping type<select {...mapping.register("mapping_type")}>
            {["EMPLOYEE", "EARNING", "PROJECT", "COST_CODE", "LABOR_CATEGORY", "LEAVE"].map((type) => <option key={type}>{type}</option>)}
          </select></label>
          <label>Effective from<input required type="date" {...mapping.register("effective_from")} /></label>
          <label>Internal key<input list="payroll-internal-keys" required {...mapping.register("internal_key")} /></label>
          <label>Provider code<input required {...mapping.register("external_code")} /></label>
        </div>
        <datalist id="payroll-internal-keys">
          {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.employee_number}</option>)}
          {projects.map((project) => <option key={project.id} value={project.id}>{project.project_number}</option>)}
          {["REGULAR", "OVERTIME", "DOUBLE_TIME", "TRAVEL", "LEAVE", "INDIRECT"].map((code) => <option key={code} value={code} />)}
        </datalist>
        <p className="field-note">Use the employee or project UUID shown by the suggestion list, or the exact earning/cost/labor key reported in preview.</p>
        <button className="quiet" disabled={pending} type="submit">Save mapping</button>
      </form>
    </section>
  );
}

function MoneyField({
  label,
  name,
  form,
}: {
  label: string;
  name: keyof PayRateInput;
  form: ReturnType<typeof useForm<PayRateInput>>;
}) {
  return <label>{label}<input min="0" required step=".0001" type="number" {...form.register(name, { valueAsNumber: true })} /></label>;
}
