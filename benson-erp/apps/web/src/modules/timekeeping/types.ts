export type TimeEntryStatus = "DRAFT" | "CERTIFIED" | "APPROVED" | "CORRECTED";

export type TimeEntryEmployeeOption = {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  is_self: boolean;
};

export type TimeEntry = {
  id: string;
  employee_id: string;
  work_date: string;
  start_at: string;
  end_at: string;
  break_minutes: number;
  total_hours: string;
  regular_hours: string;
  overtime_hours: string;
  double_time_hours: string;
  travel_hours: string;
  leave_hours: string;
  indirect_hours: string;
  uncompensated_overtime_hours: string;
  project_id: string | null;
  federal_charge_code_id: string | null;
  contract_code: string | null;
  task_order: string | null;
  clin: string | null;
  funding_line: string | null;
  charge_code: string;
  cost_code: string | null;
  labor_category: string | null;
  trade: string | null;
  location: string | null;
  description: string;
  status: TimeEntryStatus;
  source: "WEB" | "OFFLINE" | "CREW";
  client_operation_id: string;
  original_device_timestamp: string;
  server_received_at: string;
  version: number;
};

export type TimeFormFields = {
  employee_id: string;
  project_id: string;
  federal_charge_code_id: string;
  contract_code: string;
  task_order: string;
  clin: string;
  funding_line: string;
  work_date: string;
  start_time: string;
  end_time: string;
  break_minutes: number;
  regular_hours: number;
  overtime_hours: number;
  double_time_hours: number;
  travel_hours: number;
  indirect_hours: number;
  charge_code: string;
  cost_code: string;
  labor_category: string;
  trade: string;
  location: string;
  description: string;
};

export type QueuedTimeOperation = {
  id: string;
  created_at: string;
  tenant_id: string;
  user_id: string;
  payload: Record<string, unknown>;
};
