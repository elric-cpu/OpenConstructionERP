import type {
  EmployeeQualificationInput,
  FederalChargeCodeInput,
  FederalInvoiceRequest,
  FederalLaborRateInput,
} from "./types";

const nullable = (value: string | null) => value || null;

export function normalizeChargeCodeInput(
  input: FederalChargeCodeInput,
): FederalChargeCodeInput {
  return {
    ...input,
    task_order: nullable(input.task_order),
    delivery_order: nullable(input.delivery_order),
    clin: nullable(input.clin),
    slin: nullable(input.slin),
    funding_line: nullable(input.funding_line),
    project_id: nullable(input.project_id),
    cost_code: nullable(input.cost_code),
    labor_category: nullable(input.labor_category),
    active_to: nullable(input.active_to),
    required_qualification_code: nullable(input.required_qualification_code),
  };
}

export function normalizeRateInput(
  input: FederalLaborRateInput,
): FederalLaborRateInput {
  return {
    ...input,
    effective_to: nullable(input.effective_to),
    source_reference: nullable(input.source_reference),
  };
}

export function normalizeQualificationInput(
  input: EmployeeQualificationInput,
): EmployeeQualificationInput {
  return {
    ...input,
    issuer: nullable(input.issuer),
    credential_number: nullable(input.credential_number),
    evidence_document_id: nullable(input.evidence_document_id),
    effective_to: nullable(input.effective_to),
  };
}

export function normalizeInvoiceRequest(
  input: FederalInvoiceRequest,
): FederalInvoiceRequest {
  return {
    ...input,
    task_order: nullable(input.task_order),
    invoice_number: nullable(input.invoice_number),
  };
}
