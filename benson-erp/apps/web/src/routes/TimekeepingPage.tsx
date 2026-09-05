import { useEffect } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
import { Link } from "react-router-dom";

import { ApiError, getAuthScope } from "../api/client";
import { useAuth } from "../app/AuthContext";
import {
  useCreateTimeEntry,
  useOfflineTimeSync,
  useTimeEntries,
  useTimeResources,
  useTimeTransition,
} from "../modules/timekeeping/useTimekeeping";
import type { TimeEntry, TimeFormFields } from "../modules/timekeeping/types";
import type { FederalChargeCode } from "../modules/federal-labor/types";
import { canonicalFederalAllocation } from "../modules/timekeeping/federalAllocation";
import {
  canApproveEntry,
  canCertifyEntry,
  timeAccess,
} from "../modules/timekeeping/timeAccess";

const defaults: TimeFormFields = {
  employee_id: "",
  project_id: "",
  federal_charge_code_id: "",
  contract_code: "",
  task_order: "",
  clin: "",
  funding_line: "",
  work_date: new Date().toISOString().slice(0, 10),
  start_time: "08:00",
  end_time: "16:30",
  break_minutes: 30,
  regular_hours: 8,
  overtime_hours: 0,
  double_time_hours: 0,
  travel_hours: 0,
  indirect_hours: 0,
  charge_code: "DIRECT-PROJECT",
  cost_code: "",
  labor_category: "",
  trade: "",
  location: "",
  description: "",
};

function message(error: unknown) {
  return error instanceof ApiError ? error.message : "The timekeeping request failed.";
}

export function TimekeepingPage() {
  const auth = useAuth();
  const resources = useTimeResources();
  const entries = useTimeEntries();
  const sync = useOfflineTimeSync();
  const createEntry = useCreateTimeEntry(sync);
  const certify = useTimeTransition("certify");
  const approve = useTimeTransition("approve");
  const form = useForm<TimeFormFields>({ defaultValues: defaults });
  const access = timeAccess(getAuthScope()?.permissions ?? []);
  const selfEmployee = resources.employees.data?.find((employee) => employee.is_self);
  useEffect(() => {
    if (!access.canEnterTeam && selfEmployee) {
      form.setValue("employee_id", selfEmployee.id);
    }
  }, [access.canEnterTeam, form, selfEmployee]);
  const error =
    resources.employees.error ??
    resources.projects.error ??
    resources.federalChargeCodes.error ??
    entries.error ??
    createEntry.error ??
    certify.error ??
    approve.error;

  async function submit(fields: TimeFormFields) {
    await createEntry.mutateAsync({
      fields,
      offline: !sync.online || !navigator.onLine,
    });
    form.reset({
      ...defaults,
      employee_id: fields.employee_id,
      project_id: fields.project_id,
    });
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div><p className="eyebrow">Benson Construction ERP</p><h1>Daily time</h1></div>
        <div className="header-actions">
          <Link className="quiet" to="/federal-labor">Federal labor</Link>
          <Link className="quiet" to="/payroll">Payroll</Link>
          <Link className="quiet" to="/schedule">Schedule</Link>
          <Link className="quiet" to="/employees">Employees</Link>
          <button className="quiet" onClick={() => auth.logout()} type="button">Sign out</button>
        </div>
      </header>
      <SyncStatus
        online={sync.online}
        queued={sync.queued.length}
        syncing={sync.syncing}
        onSync={sync.flush}
      />
      {error && <div className="alert" role="alert">{message(error)}</div>}
      <div className="time-layout">
        <form className="form-card" onSubmit={form.handleSubmit(submit)}>
          <h2>Record all hours worked</h2>
          <div className="field-grid">
            <label className="wide">Employee<select disabled={!access.canEnterTeam} {...form.register("employee_id")}>
              {access.canEnterTeam && <option value="">Select employee</option>}
              {resources.employees.data?.map((employee) => <option key={employee.id} value={employee.id}>{employee.employee_number} · {employee.first_name} {employee.last_name}</option>)}
            </select></label>
            <label className="wide">Project<select {...form.register("project_id")}>
              <option value="">Indirect or leave time</option>
              {resources.projects.data?.map((project) => <option key={project.id} value={project.id}>{project.project_number} · {project.name}</option>)}
            </select></label>
            <FederalChargeCodeField
              codes={resources.federalChargeCodes.data ?? []}
              form={form}
            />
            <label>Work date<input required type="date" {...form.register("work_date")} /></label>
            <label>Charge code<input required {...form.register("charge_code")} /></label>
            <label>Start<input required type="time" {...form.register("start_time")} /></label>
            <label>End<input required type="time" {...form.register("end_time")} /></label>
            <NumberField label="Break minutes" name="break_minutes" form={form} />
            <NumberField label="Regular hours" name="regular_hours" form={form} />
            <NumberField label="Overtime hours" name="overtime_hours" form={form} />
            <NumberField label="Double time" name="double_time_hours" form={form} />
            <NumberField label="Travel hours" name="travel_hours" form={form} />
            <NumberField label="Indirect hours" name="indirect_hours" form={form} />
            <label>Cost code<input {...form.register("cost_code")} /></label>
            <label>Labor category<input {...form.register("labor_category")} /></label>
            <label>Trade<input {...form.register("trade")} /></label>
            <label>Location<input {...form.register("location")} /></label>
            <label className="wide">Work performed<textarea required rows={3} {...form.register("description")} /></label>
          </div>
          <button className="primary" disabled={createEntry.isPending} type="submit">
            {createEntry.isPending ? "Saving…" : sync.online ? "Save daily time" : "Queue daily time"}
          </button>
        </form>
        <TimeEntryList
          entries={entries.data ?? []}
          canApproveTeam={access.canApproveTeam}
          ownEmployeeId={selfEmployee?.id}
          onApprove={approve.mutateAsync}
          onCertify={certify.mutateAsync}
        />
      </div>
    </main>
  );
}

type Form = UseFormReturn<TimeFormFields>;

function FederalChargeCodeField({ codes, form }: { codes: FederalChargeCode[]; form: Form }) {
  function select(codeId: string) {
    const code = codes.find((item) => item.id === codeId);
    const allocation = canonicalFederalAllocation(code);
    Object.entries(allocation).forEach(([name, value]) => {
      form.setValue(name as keyof TimeFormFields, value);
    });
  }
  return (
    <label className="wide federal-time-code">
      Federal charge authorization
      <select
        {...form.register("federal_charge_code_id", {
          onChange: (event) => select(event.target.value),
        })}
      >
        <option value="">Commercial or indirect time</option>
        {codes.filter((code) => code.status === "OPEN").map((code) => (
          <option key={code.id} value={code.id}>
            {code.code} · {code.contract_code}{code.task_order ? ` / ${code.task_order}` : ""}{code.clin ? ` / ${code.clin}` : ""}
          </option>
        ))}
      </select>
      <small>Selecting a code locks the contract, project, cost, and labor allocation to its authorized hierarchy.</small>
    </label>
  );
}

function NumberField({ label, name, form }: { label: string; name: keyof TimeFormFields; form: Form }) {
  return <label>{label}<input min="0" step=".01" type="number" {...form.register(name, { valueAsNumber: true })} /></label>;
}

function SyncStatus({ online, queued, syncing, onSync }: { online: boolean; queued: number; syncing: boolean; onSync: () => Promise<void> }) {
  return <section className={`sync-status ${online ? "online" : "offline"}`} aria-live="polite"><strong>{online ? "Online" : "Offline"}</strong><span>{queued} operation{queued === 1 ? "" : "s"} waiting to sync</span>{online && queued > 0 && <button className="quiet" disabled={syncing} onClick={onSync} type="button">{syncing ? "Syncing…" : "Sync now"}</button>}</section>;
}

function TimeEntryList({ entries, ownEmployeeId, canApproveTeam, onCertify, onApprove }: { entries: TimeEntry[]; ownEmployeeId?: string; canApproveTeam: boolean; onCertify: (entry: TimeEntry) => Promise<TimeEntry>; onApprove: (entry: TimeEntry) => Promise<TimeEntry> }) {
  const access = { canApproveTeam, canEnterTeam: false };
  return <section className="form-card"><div className="card-heading"><h2>Recent entries</h2><span>{entries.length}</span></div>{entries.length === 0 && <p>No time recorded in the last 14 days.</p>}<ol className="time-entry-list">{entries.map((entry) => <li key={entry.id}><div><strong>{entry.work_date} · {entry.total_hours} hours</strong><span>{entry.charge_code} · {entry.status}</span><p>{entry.description}</p></div>{canCertifyEntry(entry, ownEmployeeId) && <button className="quiet" onClick={() => onCertify(entry)} type="button">Certify my time</button>}{canApproveEntry(entry, access) && <button className="primary" onClick={() => onApprove(entry)} type="button">Approve</button>}</li>)}</ol></section>;
}
