export type RequestStatus = "loading" | "ready" | "auth-required" | "offline";
export type ActiveView = "overview" | "leads" | "customers" | "employees" | "tasks" | "activate";
export type SpamFilter = "active" | "spam" | "all";
export type BusyState = "lead" | "save" | "draft" | "";

export type Dashboard = {
  metrics: Record<string, number>;
  attention: unknown[];
  schedule: unknown[];
  jobs: unknown[];
};

export type NotificationSettings = {
  email_enabled: true;
  sms_enabled: boolean;
  sms_configured: boolean;
};

export type Lead = {
  id: string;
  status: string;
  priority: string;
  name: string;
  phone: string;
  email: string | null;
  service_type: string;
  city: string;
  created_at: string;
  assigned_to: string | null;
  source: string;
  is_spam: boolean;
  spam_reason: string | null;
};

export type Customer = {
  id: string;
  name: string;
  company: string;
  phone: string;
  email: string | null;
  billing_address: string;
  service_address: string;
  city: string;
  state: string;
  zip_code: string;
  notes: string;
  status: "active" | "archived";
  source_lead_id: string | null;
  created_at: string;
  updated_at: string;
};

export type Attachment = {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type Note = { id: string; author: string; body: string; created_at: string };
export type AuditEvent = {
  id: string;
  event: string;
  actor: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type LeadDetail = Lead & {
  payload: Record<string, unknown>;
  attachments: Attachment[];
  notes: Note[];
  audit_events: AuditEvent[];
};

export type Skill = { id: string; label: string; description: string; risk: string };
export type StaffMember = { email: string; display_name: string; role: string };
export type Employee = {
  id: string;
  name: string;
  email: string;
  invite_delivery_email: string | null;
  start_date: string;
  work_location: string;
  classification: "employee" | "independent_contractor";
  role: string;
  federal_contract_applicability: "unknown" | "not_applicable" | "applicable";
  status: "draft" | "invited" | "active" | "onboarding_complete" | "inactive";
  workspace_account_status: "external_unlicensed_required" | "unlicensed_attested";
  workspace_license_policy: "no_paid_license";
  created_at: string;
};
export type EmployeeTask = {
  id: string;
  employee_id: string;
  requirement_id: string;
  label: string;
  responsible_party: "employee" | "employer" | "contractor";
  status: "pending" | "blocked" | "submitted" | "completed" | "rejected" | "not_applicable";
  due_date: string;
  instructions: string;
  applicability_reason: string;
  evidence_required: boolean;
  completed_at: string | null;
  completed_by: string | null;
};
export type EmployeeDocument = {
  id: string;
  employee_id: string;
  task_id: string;
  version: number;
  original_name: string;
  content_type: string;
  size_bytes: number;
  data_classification: "restricted" | "highly_restricted";
  status: "active" | "superseded";
  created_at: string;
};
export type PortalSession = {
  kind: "staff" | "employee";
  email: string;
  role: string;
  default_view: "overview" | "tasks";
  employee: Employee | null;
};
export type EditableLead = {
  name: string;
  phone: string;
  email: string;
  service_type: string;
  city: string;
  source: string;
};
