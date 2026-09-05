export type EmployeeStatus =
  | "DRAFT"
  | "IDENTITY_REQUESTED"
  | "IDENTITY_CREATED"
  | "ACTIVE"
  | "INACTIVE";

export type Employee = {
  id: string;
  employee_number: string;
  first_name: string;
  last_name: string;
  preferred_name: string | null;
  personal_email: string;
  company_username: string;
  company_email: string | null;
  hire_date: string;
  status: EmployeeStatus;
  activation_sent_at: string | null;
  erp_access_confirmed_at: string | null;
  version: number;
};

export type EmployeeActivation = {
  id: string;
  employee_id: string;
  expires_at: string;
  sent_at: string | null;
  used_at: string | null;
  revoked_at: string | null;
  attempt_count: number;
  last_attempt_at: string | null;
  version: number;
};

export type EmployeeActivationPreview = {
  activation_url: string;
  expires_at: string;
};

export type Provisioning = {
  id: string;
  employee_id: string;
  status: "PENDING" | "CREATED";
  primary_email: string;
  external_user_id: string | null;
  completed_at: string | null;
  version: number;
};

export type EmployeeInput = {
  employee_number: string;
  first_name: string;
  last_name: string;
  personal_email: string;
  company_username: string;
  hire_date: string;
};
