export type EmployeeClassification = "employee" | "independent_contractor";
export type EmployeeLifecycle = "draft" | "invited" | "active" | "onboarding_complete" | "inactive";
export type OnboardingRole = "owner" | "admin" | "office" | "estimator_pm" | "accounting" | "field" | "subcontractor";

export type OnboardingEmployee = {
  id: string;
  name: string;
  email: string;
  invite_delivery_email: string | null;
  start_date: string;
  work_location: string;
  classification: EmployeeClassification;
  role: OnboardingRole;
  federal_contract_applicability: "unknown" | "not_applicable" | "applicable";
  status: EmployeeLifecycle;
  workspace_account_status: "external_unlicensed_required" | "unlicensed_attested";
  workspace_license_policy: "no_paid_license";
  version: number;
  created_at: string;
};

export type OnboardingTask = {
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
  completion_method: "document_upload" | "employee_signature" | "employer_evidence" | "manual_review";
  applicability_review_required: boolean;
  applicability_status: "applied" | "pending_review" | "not_applicable";
  retention_rule: string;
  data_classification: "internal" | "confidential" | "restricted" | "highly_restricted";
  data_category: "identity_i9" | "tax" | "banking" | "medical_disability" | "veteran" | "general";
  official_source: string;
  legal_review_status: "pending" | "approved";
  signature_statement: string | null;
  applicability_decided_at: string | null;
  applicability_decided_by: string | null;
  rule_version: string;
  completed_at: string | null;
  completed_by: string | null;
  latest_rejection_reason: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type OnboardingDocument = {
  id: string;
  employee_id: string;
  task_id: string;
  version: number;
  original_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  data_classification: "restricted" | "highly_restricted";
  status: "active" | "superseded";
  uploaded_by: string;
  created_at: string;
};

export type OnboardingSignature = {
  id: string;
  employee_id: string;
  task_id: string;
  version: number;
  signer_email: string;
  typed_name: string;
  statement_version: string;
  statement_hash: string;
  status: "active" | "superseded";
  signed_at: string;
};

export type IdentityProvisioningCommand = {
  id: string;
  employee_id: string;
  kind: "create" | "suspend";
  status:
    | "pending_approval"
    | "manual_setup_required"
    | "approved"
    | "executing"
    | "verified"
    | "admin_confirmation_required"
    | "admin_confirmed"
    | "failed"
    | "manual_review_required"
    | "suspended";
  version: number;
  target_email: string;
  target_org_unit: string;
  external_user_id: string | null;
  failure_code: string | null;
  created_at: string;
  updated_at: string;
};

export type RetentionHold = {
  id: string;
  employee_id: string;
  reason: string;
  created_by: string;
  created_at: string;
  released_by: string | null;
  released_at: string | null;
};

export type OnboardingTaskPayload = {
  default_view: "tasks";
  employee: OnboardingEmployee;
  tasks: OnboardingTask[];
  progress: { completed: number; total: number };
};

export type NewEmployeeInput = Pick<
  OnboardingEmployee,
  "name" | "email" | "start_date" | "work_location" | "classification" | "role" | "federal_contract_applicability"
> & { invite_delivery_email: string };

export type TaskReviewInput = {
  expected_version: number;
  decision: "complete" | "reject";
  comment: string;
};

export type ApplicabilityReviewInput = {
  expected_version: number;
  decision: "applicable" | "not_applicable";
  comment: string;
  reviewer_name: string;
  reviewer_qualification: string;
  legal_review_confirmed: true;
};
