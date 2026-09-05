export type FederalComplianceProfile =
  | "COMMERCIAL"
  | "FEDERAL_FIXED_PRICE"
  | "FEDERAL_COST_REIMBURSEMENT"
  | "FEDERAL_TIME_AND_MATERIALS"
  | "FEDERAL_LABOR_HOUR"
  | "FEDERAL_CONSTRUCTION_WAGE_RATE"
  | "FEDERAL_SERVICE_CONTRACT_LABOR"
  | "STATE_PREVAILING_WAGE"
  | "CUSTOM_COMPLIANCE_PROFILE";

export type FederalChargeCodeInput = {
  code: string;
  name: string;
  profile: FederalComplianceProfile;
  agency_code: string;
  contract_code: string;
  task_order: string | null;
  delivery_order: string | null;
  clin: string | null;
  slin: string | null;
  funding_line: string | null;
  project_id: string | null;
  cost_code: string | null;
  labor_category: string | null;
  active_from: string;
  active_to: string | null;
  required_qualification_code: string | null;
};

export type FederalChargeCode = FederalChargeCodeInput & {
  id: string;
  status: "OPEN" | "CLOSED";
  closed_at: string | null;
  closed_by: string | null;
  closed_reason: string | null;
  version: number;
};

export type FederalLaborRateInput = {
  federal_charge_code_id: string;
  labor_category: string;
  regular_bill_rate: number;
  overtime_bill_rate: number;
  double_time_bill_rate: number;
  currency: string;
  source_reference: string | null;
  effective_from: string;
  effective_to: string | null;
};

export type FederalLaborRate = Omit<
  FederalLaborRateInput,
  "regular_bill_rate" | "overtime_bill_rate" | "double_time_bill_rate"
> & {
  id: string;
  regular_bill_rate: string;
  overtime_bill_rate: string;
  double_time_bill_rate: string;
  version: number;
};

export type EmployeeQualificationInput = {
  employee_id: string;
  qualification_code: string;
  qualification_name: string;
  status: "ACTIVE" | "SUSPENDED" | "REVOKED";
  issuer: string | null;
  credential_number: string | null;
  evidence_document_id: string | null;
  effective_from: string;
  effective_to: string | null;
};

export type EmployeeQualification = EmployeeQualificationInput & {
  id: string;
  verified_at: string | null;
  verified_by: string | null;
  version: number;
};

export type FederalInvoiceRequest = {
  contract_code: string;
  task_order: string | null;
  invoice_number: string | null;
  invoice_period_start: string;
  invoice_period_end: string;
};

export type FederalInvoiceException = {
  code: string;
  message: string;
  time_entry_id: string | null;
  blocking: boolean;
};

export type FederalInvoiceLine = {
  id?: string;
  time_entry_id: string;
  employee_id: string;
  employee_name: string;
  work_date: string;
  federal_charge_code_id: string;
  agency_code: string;
  contract_code: string;
  task_order: string | null;
  clin: string | null;
  funding_line: string | null;
  labor_category: string;
  approved_hours: string;
  regular_hours: string;
  overtime_hours: string;
  double_time_hours: string;
  regular_bill_rate: string;
  overtime_bill_rate: string;
  double_time_bill_rate: string;
  extended_amount: string;
  qualification_status: string;
  payroll_reconciliation_status: string;
};

export type FederalInvoicePreview = {
  lines: FederalInvoiceLine[];
  total_approved_hours: string;
  total_extended_amount: string;
  exceptions: FederalInvoiceException[];
  ready: boolean;
};

export type FederalInvoiceSupport = {
  id: string;
  contract_code: string;
  task_order: string | null;
  invoice_number: string | null;
  invoice_period_start: string;
  invoice_period_end: string;
  artifact_version: number;
  status: "GENERATED";
  generated_at: string;
  generated_by: string;
  total_approved_hours: string;
  total_extended_amount: string;
  content_checksum: string;
  version: number;
  lines: FederalInvoiceLine[];
};

export type FloorCheckEntry = {
  employee_id: string;
  employee_name: string;
  work_date: string;
  location: string | null;
  description: string;
  contract_code: string;
  task_order: string | null;
  clin: string | null;
  labor_category: string;
  approved_hours: string;
  certified_at: string;
  approved_at: string;
  approved_by: string;
  payroll_status: string;
  invoice_status: string;
};

export type FloorCheckReport = {
  period_start: string;
  period_end: string;
  entries: FloorCheckEntry[];
};
