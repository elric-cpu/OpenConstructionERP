import { useState } from "react";

import { api } from "../../api/client";
import type { WorkflowFields } from "./workflowSchema";

type Lead = { id: string; version: number; status: string };
type Conversion = { customer_id: string; property_id: string };
type Estimate = { id: string; version: number; total: string; status: string };
type Proposal = {
  id: string;
  version: number;
  status: string;
  price_snapshot: { total: string };
  document_checksum: string;
};
type ProjectResult = {
  project: { id: string; project_number: string; name: string };
  contract_value: string;
  budget_line_count: number;
};

export type WorkflowStage =
  | "INTAKE"
  | "LEAD"
  | "QUALIFIED"
  | "CONVERTED"
  | "ESTIMATE"
  | "PRICED"
  | "APPROVED"
  | "PROPOSAL"
  | "ACCEPTED"
  | "PROJECT";

export function useLeadToProject() {
  const [stage, setStage] = useState<WorkflowStage>("INTAKE");
  const [lead, setLead] = useState<Lead | null>(null);
  const [conversion, setConversion] = useState<Conversion | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [project, setProject] = useState<ProjectResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The operation failed");
    } finally {
      setBusy(false);
    }
  }

  return {
    stage,
    lead,
    conversion,
    estimate,
    proposal,
    project,
    busy,
    error,
    createLead: (fields: WorkflowFields) =>
      run(async () => {
        const result = await api.post<Lead>("/leads", {
          contact_name: fields.contactName,
          email: fields.email,
          phone: fields.phone || null,
          source: fields.source,
          summary: fields.summary,
        });
        setLead(result);
        setStage("LEAD");
      }),
    qualify: (fields: WorkflowFields) =>
      run(async () => {
        if (!lead) return;
        const result = await api.post<Lead>(`/leads/${lead.id}/qualify`, {
          reason: fields.qualificationReason,
          expected_version: lead.version,
        });
        setLead(result);
        setStage("QUALIFIED");
      }),
    convert: (fields: WorkflowFields) =>
      run(async () => {
        if (!lead) return;
        const result = await api.post<Conversion>(`/leads/${lead.id}/convert`, {
          property: {
            address_line_1: fields.address,
            city: fields.city,
            state: fields.state,
            postal_code: fields.postalCode,
          },
          expected_version: lead.version,
        });
        setConversion(result);
        setStage("CONVERTED");
      }),
    createEstimate: (fields: WorkflowFields) =>
      run(async () => {
        if (!lead) return;
        const result = await api.post<Estimate>("/estimates", {
          lead_id: lead.id,
          pricing_mode: fields.pricingMode,
          pricing_rate: String(fields.pricingRate / 100),
          tax_rate: String(fields.taxRate / 100),
        });
        setEstimate(result);
        setStage("ESTIMATE");
      }),
    addLine: (fields: WorkflowFields) =>
      run(async () => {
        if (!estimate) return;
        const result = await api.post<Estimate>(`/estimates/${estimate.id}/lines`, {
          section_title: fields.sectionTitle,
          description: fields.lineDescription,
          quantity: String(fields.quantity),
          unit: fields.unit,
          unit_cost: String(fields.unitCost),
          category: fields.costCategory,
          position: 1,
          expected_version: estimate.version,
        });
        setEstimate(result);
        setStage("PRICED");
      }),
    approve: () =>
      run(async () => {
        if (!estimate) return;
        const result = await api.post<Estimate>(
          `/estimates/${estimate.id}/approve`,
          undefined,
          { "If-Match": String(estimate.version) },
        );
        setEstimate(result);
        setStage("APPROVED");
      }),
    createProposal: () =>
      run(async () => {
        if (!estimate) return;
        const result = await api.post<Proposal>(`/estimates/${estimate.id}/proposals`);
        setProposal(result);
        setStage("PROPOSAL");
      }),
    viewProposal: () =>
      run(async () => {
        if (!proposal) return;
        const blob = await api.blob(`/proposals/${proposal.id}/document`);
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank", "noopener,noreferrer");
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }),
    accept: (fields: WorkflowFields) =>
      run(async () => {
        if (!proposal) return;
        if (!fields.proposalConsent) throw new Error("Review and consent to the proposal first");
        const result = await api.post<Proposal>(`/proposals/${proposal.id}/accept`, {
          accepted_by_name: fields.contactName,
          consent: fields.proposalConsent,
          acceptance_statement:
            "I accept this proposal and authorize the described construction work.",
          expected_version: proposal.version,
        });
        setProposal(result);
        setStage("ACCEPTED");
      }),
    createProject: (fields: WorkflowFields) =>
      run(async () => {
        if (!proposal) return;
        const result = await api.post<ProjectResult>(`/proposals/${proposal.id}/create-project`, {
          name: fields.projectName,
          project_number: fields.projectNumber,
          contract_number: fields.contractNumber,
        });
        setProject(result);
        setStage("PROJECT");
      }),
  };
}
