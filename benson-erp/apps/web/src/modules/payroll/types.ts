export type PayrollPeriodStatus =
  | "OPEN"
  | "EMPLOYEE_REVIEW"
  | "SUPERVISOR_REVIEW"
  | "PAYROLL_REVIEW"
  | "LOCKED"
  | "EXPORTED"
  | "PROCESSED"
  | "RECONCILED";

export type PayrollPeriod = {
  id: string;
  period_start: string;
  period_end: string;
  pay_date: string;
  status: PayrollPeriodStatus;
  workweek_definition: string;
  provider: string;
  export_status: string;
  reconciliation_status: string;
  version: number;
};

export type PayrollPeriodInput = {
  period_start: string;
  period_end: string;
  pay_date: string;
  workweek_definition: string;
  provider: string;
};

export type PayrollException = {
  code: string;
  message: string;
  time_entry_id: string | null;
  employee_id: string | null;
  internal_key: string | null;
};

export type PayrollPreviewEmployee = {
  employee_id: string;
  employee_number: string;
  employee_name: string;
  regular_hours: string;
  overtime_hours: string;
  double_time_hours: string;
  travel_hours: string;
  leave_hours: string;
  indirect_hours: string;
  estimated_gross_labor: string | null;
  source_time_entry_ids: string[];
};

export type PayrollPreview = {
  payroll_period_id: string;
  provider: string;
  approved_entry_count: number;
  unapproved_entry_count: number;
  employees: PayrollPreviewEmployee[];
  exceptions: PayrollException[];
  totals: Record<string, string | number | null>;
  calculation: Record<string, string>;
  ready_to_lock: boolean;
};

export type PayrollExport = {
  id: string;
  payroll_period_id: string;
  provider: string;
  format: "CSV" | "XLSX" | "JSON";
  artifact_version: number;
  generated_at: string;
  file_checksum: string;
  filename: string;
  content_type: string;
  includes_sensitive_fields: boolean;
  totals_snapshot: Record<string, unknown>;
  status: string;
  version: number;
};

export type PayRateInput = {
  employee_id: string;
  effective_from: string;
  effective_to: string | null;
  base_rate: number;
  overtime_rate: number;
  double_time_rate: number;
  fringe_rate: number;
  cash_in_lieu_rate: number;
};

export type PayrollMappingInput = {
  provider: string;
  mapping_type:
    | "EMPLOYEE"
    | "EARNING"
    | "PROJECT"
    | "COST_CODE"
    | "LABOR_CATEGORY"
    | "LEAVE";
  internal_key: string;
  external_code: string;
  effective_from: string;
  effective_to: string | null;
  configuration: Record<string, unknown>;
};

export type PayrollResultLineInput = {
  time_entry_id: string;
  provider_employee_id: string;
  provider_payroll_id?: string | null;
  payment_reference?: string | null;
  work_date: string;
  pay_date: string;
  regular_hours: string;
  overtime_hours: string;
  double_time_hours: string;
  travel_hours?: string;
  leave_hours?: string;
  indirect_hours?: string;
  base_rate: string;
  overtime_rate: string;
  double_time_rate: string;
  gross_wages: string;
  employer_taxes?: string;
  employee_deductions?: string;
  employer_benefits?: string;
  workers_compensation?: string;
  fringe_benefits?: string;
  net_pay: string;
  is_adjustment?: boolean;
};

export type PayrollResultImport = {
  id: string;
  payroll_period_id: string;
  payroll_export_id: string;
  provider: string;
  provider_reference: string;
  source_checksum: string;
  imported_at: string;
  status: "IMPORTED" | "EXCEPTIONS" | "RECONCILED";
  reconciliation_summary: Record<string, string | number> | null;
  reconciled_at: string | null;
  version: number;
};

export type ReconciliationException = {
  id: string;
  payroll_result_line_id: string | null;
  code: string;
  message: string;
  expected_value: string | null;
  actual_value: string | null;
  status: "OPEN" | "RESOLVED";
  version: number;
};

export type PayrollReconciliation = {
  result_import: PayrollResultImport;
  exceptions: ReconciliationException[];
  job_cost_count: number;
  job_cost_total: string;
  calculation: Record<string, string>;
};
