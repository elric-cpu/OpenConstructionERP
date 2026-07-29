import { useForm } from "react-hook-form";

import type { Employee } from "../people/types";
import type { Project } from "../scheduling/types";
import type {
  EmployeeQualificationInput,
  EmployeeQualification,
  FederalChargeCode,
  FederalChargeCodeInput,
  FederalComplianceProfile,
  FederalLaborRate,
  FederalLaborRateInput,
} from "./types";

const today = new Date().toISOString().slice(0, 10);
const profiles: FederalComplianceProfile[] = [
  "FEDERAL_FIXED_PRICE",
  "FEDERAL_COST_REIMBURSEMENT",
  "FEDERAL_TIME_AND_MATERIALS",
  "FEDERAL_LABOR_HOUR",
  "FEDERAL_CONSTRUCTION_WAGE_RATE",
  "FEDERAL_SERVICE_CONTRACT_LABOR",
  "STATE_PREVAILING_WAGE",
  "COMMERCIAL",
  "CUSTOM_COMPLIANCE_PROFILE",
];

export function FederalChargeCodePanel({
  codes,
  projects,
  pending,
  onCreate,
}: {
  codes: FederalChargeCode[];
  projects: Project[];
  pending: boolean;
  onCreate: (input: FederalChargeCodeInput) => Promise<unknown>;
}) {
  const form = useForm<FederalChargeCodeInput>({
    defaultValues: {
      code: "",
      name: "",
      profile: "FEDERAL_FIXED_PRICE",
      agency_code: "",
      contract_code: "",
      task_order: null,
      delivery_order: null,
      clin: null,
      slin: null,
      funding_line: null,
      project_id: null,
      cost_code: null,
      labor_category: null,
      active_from: today,
      active_to: null,
      required_qualification_code: null,
    },
  });
  return (
    <section className="federal-columns">
      <form className="form-card federal-setup-card" onSubmit={form.handleSubmit(onCreate)}>
        <div className="card-heading">
          <div><p className="eyebrow">Hierarchy control</p><h2>Open a charge code</h2></div>
          <span>Agency → labor</span>
        </div>
        <div className="field-grid">
          <label>Internal code<input required {...form.register("code")} /></label>
          <label>Name<input required {...form.register("name")} /></label>
          <label className="wide">Compliance profile<select {...form.register("profile")}>
            {profiles.map((profile) => <option key={profile}>{profile}</option>)}
          </select></label>
          <label>Agency<input required {...form.register("agency_code")} /></label>
          <label>Contract<input required {...form.register("contract_code")} /></label>
          <label>Task order<input {...form.register("task_order")} /></label>
          <label>Delivery order<input {...form.register("delivery_order")} /></label>
          <label>CLIN<input {...form.register("clin")} /></label>
          <label>SLIN<input {...form.register("slin")} /></label>
          <label>Funding line<input {...form.register("funding_line")} /></label>
          <label>Project<select {...form.register("project_id")}>
            <option value="">No linked project</option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.project_number} · {project.name}</option>)}
          </select></label>
          <label>Cost code<input {...form.register("cost_code")} /></label>
          <label>Labor category<input {...form.register("labor_category")} /></label>
          <label>Required qualification<input {...form.register("required_qualification_code")} /></label>
          <label>Active from<input required type="date" {...form.register("active_from")} /></label>
          <label>Active through<input type="date" {...form.register("active_to")} /></label>
        </div>
        <button className="primary" disabled={pending} type="submit">Open charge code</button>
      </form>
      <section className="form-card">
        <div className="card-heading"><div><p className="eyebrow">Authorized work</p><h2>Charge-code register</h2></div><span>{codes.length}</span></div>
        {codes.length === 0 && <p>No federal charge codes have been configured.</p>}
        <ol className="federal-register">
          {codes.map((code) => (
            <li key={code.id}>
              <div><strong>{code.code} · {code.name}</strong><span>{code.agency_code} / {code.contract_code}{code.task_order ? ` / ${code.task_order}` : ""}</span></div>
              <div className="register-meta"><span className={`status-pill ${code.status === "OPEN" ? "ready" : ""}`}>{code.status}</span><small>{code.clin || "No CLIN"} · {code.labor_category || "Any labor"}</small></div>
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}

export function FederalRateQualificationPanel({
  codes,
  employees,
  rates,
  qualifications,
  pending,
  onRate,
  onQualification,
}: {
  codes: FederalChargeCode[];
  employees: Employee[];
  rates: FederalLaborRate[];
  qualifications: EmployeeQualification[];
  pending: boolean;
  onRate: (input: FederalLaborRateInput) => Promise<unknown>;
  onQualification: (input: EmployeeQualificationInput) => Promise<unknown>;
}) {
  const rate = useForm<FederalLaborRateInput>({
    defaultValues: {
      federal_charge_code_id: "",
      labor_category: "",
      regular_bill_rate: 0,
      overtime_bill_rate: 0,
      double_time_bill_rate: 0,
      currency: "USD",
      source_reference: null,
      effective_from: today,
      effective_to: null,
    },
  });
  const qualification = useForm<EmployeeQualificationInput>({
    defaultValues: {
      employee_id: "",
      qualification_code: "",
      qualification_name: "",
      status: "ACTIVE",
      issuer: null,
      credential_number: null,
      evidence_document_id: null,
      effective_from: today,
      effective_to: null,
    },
  });
  return (
    <>
    <section className="setup-grid">
      <form className="form-card" onSubmit={rate.handleSubmit(onRate)}>
        <p className="eyebrow">Billing, not wages</p><h2>Date-effective contract rate</h2>
        <label>Charge code<select required {...rate.register("federal_charge_code_id")}>
          <option value="">Select code</option>
          {codes.filter((code) => code.status === "OPEN").map((code) => <option key={code.id} value={code.id}>{code.code} · {code.contract_code}</option>)}
        </select></label>
        <div className="field-grid">
          <label>Labor category<input required {...rate.register("labor_category")} /></label>
          <label>Effective from<input required type="date" {...rate.register("effective_from")} /></label>
          <RateField form={rate} label="Regular bill rate" name="regular_bill_rate" />
          <RateField form={rate} label="Overtime bill rate" name="overtime_bill_rate" />
          <RateField form={rate} label="Double-time bill rate" name="double_time_bill_rate" />
          <label>Source reference<input {...rate.register("source_reference")} /></label>
        </div>
        <p className="field-note">Contract bill rates remain separate from employee pay rates and actual job cost.</p>
        <button className="quiet" disabled={pending} type="submit">Save bill rate</button>
      </form>
      <form className="form-card" onSubmit={qualification.handleSubmit(onQualification)}>
        <p className="eyebrow">Date-sensitive eligibility</p><h2>Employee qualification</h2>
        <label>Employee<select required {...qualification.register("employee_id")}>
          <option value="">Select employee</option>
          {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.employee_number} · {employee.first_name} {employee.last_name}</option>)}
        </select></label>
        <div className="field-grid">
          <label>Qualification code<input required {...qualification.register("qualification_code")} /></label>
          <label>Qualification name<input required {...qualification.register("qualification_name")} /></label>
          <label>Status<select {...qualification.register("status")}>{["ACTIVE", "SUSPENDED", "REVOKED"].map((status) => <option key={status}>{status}</option>)}</select></label>
          <label>Issuer<input {...qualification.register("issuer")} /></label>
          <label>Credential number<input {...qualification.register("credential_number")} /></label>
          <label>Effective from<input required type="date" {...qualification.register("effective_from")} /></label>
          <label>Effective through<input type="date" {...qualification.register("effective_to")} /></label>
        </div>
        <button className="quiet" disabled={pending} type="submit">Save qualification</button>
      </form>
    </section>
    <FederalEligibilityRegister
      codes={codes}
      employees={employees}
      qualifications={qualifications}
      rates={rates}
    />
    </>
  );
}

function FederalEligibilityRegister({
  codes,
  employees,
  qualifications,
  rates,
}: {
  codes: FederalChargeCode[];
  employees: Employee[];
  qualifications: EmployeeQualification[];
  rates: FederalLaborRate[];
}) {
  const codeName = (id: string) => codes.find((item) => item.id === id)?.code ?? id;
  const employeeName = (id: string) => {
    const employee = employees.find((item) => item.id === id);
    return employee ? `${employee.first_name} ${employee.last_name}` : id;
  };
  return (
    <section className="setup-grid federal-register-grid">
      <section className="form-card">
        <div className="card-heading"><h2>Contract rate history</h2><span>{rates.length}</span></div>
        <ol className="federal-register">{rates.map((rate) => <li key={rate.id}><div><strong>{codeName(rate.federal_charge_code_id)} · {rate.labor_category}</strong><span>Effective {rate.effective_from}{rate.effective_to ? ` – ${rate.effective_to}` : " onward"}</span></div><div className="register-meta"><strong>${rate.regular_bill_rate}/hr</strong><small>OT ${rate.overtime_bill_rate} · DT ${rate.double_time_bill_rate}</small></div></li>)}</ol>
        {rates.length === 0 && <p>No contract bill rates are on file.</p>}
      </section>
      <section className="form-card">
        <div className="card-heading"><h2>Qualification register</h2><span>{qualifications.length}</span></div>
        <ol className="federal-register">{qualifications.map((item) => <li key={item.id}><div><strong>{employeeName(item.employee_id)}</strong><span>{item.qualification_code} · {item.qualification_name}</span></div><div className="register-meta"><span className={`status-pill ${item.status === "ACTIVE" ? "ready" : ""}`}>{item.status}</span><small>{item.effective_from}{item.effective_to ? ` – ${item.effective_to}` : " onward"}</small></div></li>)}</ol>
        {qualifications.length === 0 && <p>No employee qualifications are on file.</p>}
      </section>
    </section>
  );
}

function RateField({
  form,
  label,
  name,
}: {
  form: ReturnType<typeof useForm<FederalLaborRateInput>>;
  label: string;
  name: "regular_bill_rate" | "overtime_bill_rate" | "double_time_bill_rate";
}) {
  return <label>{label}<input min="0" required step=".0001" type="number" {...form.register(name, { valueAsNumber: true })} /></label>;
}
