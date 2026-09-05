import { useForm, type UseFormReturn } from "react-hook-form";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../app/AuthContext";
import { useLeadToProject, type WorkflowStage } from "../modules/sales/useLeadToProject";
import { workflowSchema, type WorkflowFields } from "../modules/sales/workflowSchema";

const defaults: WorkflowFields = {
  contactName: "",
  email: "",
  phone: "",
  source: "WEBSITE",
  summary: "",
  qualificationReason: "Property and project needs confirmed",
  address: "",
  city: "Burns",
  state: "OR",
  postalCode: "",
  pricingMode: "MARKUP",
  pricingRate: 20,
  taxRate: 0,
  sectionTitle: "01 General Requirements",
  lineDescription: "",
  quantity: 1,
  unit: "EA",
  unitCost: 0,
  costCategory: "OTHER",
  projectName: "",
  projectNumber: "",
  contractNumber: "",
  proposalConsent: false,
};

export function LeadToProjectPage() {
  const auth = useAuth();
  const workflow = useLeadToProject();
  const form = useForm<WorkflowFields>({ defaultValues: defaults });

  function validated(action: (fields: WorkflowFields) => Promise<void>) {
    return async () => {
      const parsed = workflowSchema.safeParse(form.getValues());
      if (!parsed.success) {
        parsed.error.issues.forEach((issue) => {
          const name = issue.path[0] as keyof WorkflowFields;
          form.setError(name, { message: issue.message });
        });
        return;
      }
      form.clearErrors();
      await action(parsed.data);
    };
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Benson Construction ERP</p>
          <h1>Lead to project</h1>
        </div>
        <div className="header-actions"><Link className="quiet" to="/time">Time</Link><Link className="quiet" to="/payroll">Payroll</Link><Link className="quiet" to="/schedule">Schedule</Link><Link className="quiet" to="/employees">Employees</Link><Link className="quiet" to="/settings/security">Security</Link><button className="quiet" onClick={() => auth.logout()} type="button">Sign out</button></div>
      </header>
      <StageRail current={workflow.stage} />
      {workflow.error && <div className="alert">{workflow.error}</div>}
      {workflow.project ? (
        <section className="success-card" aria-live="polite">
          <p className="eyebrow">Project created</p>
          <h2>{workflow.project.project.name}</h2>
          <dl>
            <div><dt>Project</dt><dd>{workflow.project.project.project_number}</dd></div>
            <div><dt>Contract value</dt><dd>${workflow.project.contract_value}</dd></div>
            <div><dt>Budget lines</dt><dd>{workflow.project.budget_line_count}</dd></div>
          </dl>
        </section>
      ) : (
        <form className="workflow-grid" onSubmit={(event) => event.preventDefault()}>
          <ContactSection form={form} />
          <PropertySection form={form} />
          <EstimateSection form={form} total={workflow.estimate?.total} />
          {workflow.stage === "PROPOSAL" && (
            <ProposalReview
              checksum={workflow.proposal?.document_checksum}
              form={form}
              onView={workflow.viewProposal}
            />
          )}
          <ProjectSection form={form} />
        </form>
      )}
      {!workflow.project && (
        <ActionBar
          busy={workflow.busy}
          stage={workflow.stage}
          actions={{
            INTAKE: validated(workflow.createLead),
            LEAD: validated(workflow.qualify),
            QUALIFIED: validated(workflow.convert),
            CONVERTED: validated(workflow.createEstimate),
            ESTIMATE: validated(workflow.addLine),
            PRICED: workflow.approve,
            APPROVED: workflow.createProposal,
            PROPOSAL: validated(workflow.accept),
            ACCEPTED: validated(workflow.createProject),
          }}
        />
      )}
    </main>
  );
}

type Form = UseFormReturn<WorkflowFields>;

function ContactSection({ form }: { form: Form }) {
  return <section className="form-card"><h2>Customer and request</h2><div className="field-grid">
    <Field label="Customer name" error={form.formState.errors.contactName?.message}><input {...form.register("contactName")} /></Field>
    <Field label="Email" error={form.formState.errors.email?.message}><input type="email" {...form.register("email")} /></Field>
    <Field label="Phone"><input {...form.register("phone")} /></Field>
    <Field label="Lead source"><select {...form.register("source")}><option>WEBSITE</option><option>PHONE</option><option>REFERRAL</option><option>GOOGLE</option><option>META</option></select></Field>
    <Field label="Project request" wide error={form.formState.errors.summary?.message}><textarea rows={3} {...form.register("summary")} /></Field>
    <Field label="Qualification reason" wide><input {...form.register("qualificationReason")} /></Field>
  </div></section>;
}

function PropertySection({ form }: { form: Form }) {
  return <section className="form-card"><h2>Property</h2><div className="field-grid">
    <Field label="Street address" wide error={form.formState.errors.address?.message}><input {...form.register("address")} /></Field>
    <Field label="City"><input {...form.register("city")} /></Field>
    <Field label="State"><input maxLength={2} {...form.register("state")} /></Field>
    <Field label="ZIP code"><input {...form.register("postalCode")} /></Field>
  </div></section>;
}

function EstimateSection({ form, total }: { form: Form; total?: string }) {
  return <section className="form-card"><div className="card-heading"><h2>Estimate</h2>{total && <strong>${total}</strong>}</div><div className="field-grid">
    <Field label="Pricing method"><select {...form.register("pricingMode")}><option value="MARKUP">Markup</option><option value="MARGIN">Margin</option></select></Field>
    <Field label="Rate %"><input type="number" step="0.01" {...form.register("pricingRate", { valueAsNumber: true })} /></Field>
    <Field label="Tax %"><input type="number" step="0.01" {...form.register("taxRate", { valueAsNumber: true })} /></Field>
    <Field label="Section"><input {...form.register("sectionTitle")} /></Field>
    <Field label="Scope description" wide error={form.formState.errors.lineDescription?.message}><input {...form.register("lineDescription")} /></Field>
    <Field label="Quantity"><input type="number" step="0.01" {...form.register("quantity", { valueAsNumber: true })} /></Field>
    <Field label="Unit"><input {...form.register("unit")} /></Field>
    <Field label="Unit cost"><input type="number" step="0.01" {...form.register("unitCost", { valueAsNumber: true })} /></Field>
    <Field label="Cost category"><select {...form.register("costCategory")}><option>LABOR</option><option>MATERIAL</option><option>EQUIPMENT</option><option>SUBCONTRACTOR</option><option>OTHER</option></select></Field>
  </div></section>;
}

function ProjectSection({ form }: { form: Form }) {
  return <section className="form-card"><h2>Contract and project</h2><div className="field-grid">
    <Field label="Project name"><input {...form.register("projectName")} /></Field>
    <Field label="Project number"><input {...form.register("projectNumber")} /></Field>
    <Field label="Contract number"><input {...form.register("contractNumber")} /></Field>
  </div></section>;
}

function ProposalReview({
  checksum,
  form,
  onView,
}: {
  checksum?: string;
  form: Form;
  onView: () => Promise<void>;
}) {
  return (
    <section className="form-card">
      <div className="card-heading">
        <h2>Proposal review</h2>
        <button className="quiet" onClick={onView} type="button">View PDF</button>
      </div>
      <p>The accepted record will be bound to this immutable proposal PDF.</p>
      <p className="document-checksum">Document SHA-256: {checksum}</p>
      <label>
        <input type="checkbox" {...form.register("proposalConsent")} />
        I reviewed and accept the proposal and authorize the described construction work.
      </label>
    </section>
  );
}

function Field({ label, error, wide, children }: { label: string; error?: string; wide?: boolean; children: ReactNode }) {
  return <label className={wide ? "wide" : ""}>{label}{children}<span className="field-error">{error}</span></label>;
}

const stages: WorkflowStage[] = ["INTAKE", "LEAD", "QUALIFIED", "CONVERTED", "ESTIMATE", "PRICED", "APPROVED", "PROPOSAL", "ACCEPTED", "PROJECT"];

function StageRail({ current }: { current: WorkflowStage }) {
  const currentIndex = stages.indexOf(current);
  return <ol className="stage-rail" aria-label="Workflow progress">{stages.map((stage, index) => <li className={index <= currentIndex ? "complete" : ""} key={stage}>{stage.replaceAll("_", " ")}</li>)}</ol>;
}

const labels: Partial<Record<WorkflowStage, string>> = { INTAKE: "Create lead", LEAD: "Qualify lead", QUALIFIED: "Create customer and property", CONVERTED: "Start estimate", ESTIMATE: "Add estimate line", PRICED: "Approve estimate", APPROVED: "Issue proposal", PROPOSAL: "Record acceptance", ACCEPTED: "Create contract and project" };

function ActionBar({ stage, busy, actions }: { stage: WorkflowStage; busy: boolean; actions: Partial<Record<WorkflowStage, () => Promise<void>>> }) {
  const action = actions[stage];
  return <footer className="action-bar"><div><span>Current step</span><strong>{stage.replaceAll("_", " ")}</strong></div>{action && <button className="primary" disabled={busy} onClick={action} type="button">{busy ? "Saving…" : labels[stage]}</button>}</footer>;
}
