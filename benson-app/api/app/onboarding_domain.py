from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from .domain import Role


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    invite_delivery_email: EmailStr | None = None
    start_date: date
    work_location: str = Field(min_length=1, max_length=200)
    classification: Literal["employee", "independent_contractor"]
    role: Role
    federal_contract_applicability: Literal[
        "unknown", "not_applicable", "applicable"
    ] = "unknown"
    phone: str = Field(default="", max_length=20)

    @model_validator(mode="after")
    def classification_matches_role(self) -> "EmployeeCreate":
        if (
            self.classification == "independent_contractor"
            and self.role is not Role.SUBCONTRACTOR
        ):
            raise ValueError("Independent contractors must use the subcontractor role")
        if self.classification == "employee" and self.role in {
            Role.SUBCONTRACTOR,
            Role.CUSTOMER,
        }:
            raise ValueError("Employees must use a staff role")
        if (
            self.classification == "employee"
            and self.email is not None
            and str(self.invite_delivery_email).casefold() == str(self.email).casefold()
        ):
            raise ValueError(
                "Employees require a separate reachable invitation delivery email"
            )
        return self


class EmployeeSummary(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    invite_delivery_email: EmailStr | None = None
    start_date: date
    work_location: str
    classification: Literal["employee", "independent_contractor"]
    role: Role
    federal_contract_applicability: Literal["unknown", "not_applicable", "applicable"]
    status: Literal["draft", "invited", "active", "onboarding_complete", "inactive"]
    workspace_account_status: Literal[
        "external_unlicensed_required", "unlicensed_attested"
    ] = "external_unlicensed_required"
    workspace_license_policy: Literal["no_paid_license"] = "no_paid_license"
    created_at: datetime
    phone: str = ""


class PortalSession(BaseModel):
    kind: Literal["staff", "employee"]
    email: EmailStr
    role: Role
    default_view: Literal["overview", "tasks"]
    employee: EmployeeSummary | None = None


class EmployeeInviteReceipt(BaseModel):
    id: UUID
    employee_id: UUID
    status: Literal["pending_delivery"] = "pending_delivery"
    expires_at: datetime


class EmployeeInviteActivation(BaseModel):
    token: str = Field(min_length=32, max_length=500)
    credential: str = Field(min_length=20, max_length=10_000)


class EmployeeTaskSummary(BaseModel):
    id: UUID
    employee_id: UUID
    requirement_id: str
    label: str
    responsible_party: Literal["employee", "employer", "contractor"]
    status: Literal[
        "pending", "blocked", "submitted", "completed", "rejected", "not_applicable"
    ]
    due_date: date
    instructions: str
    applicability_reason: str
    evidence_required: bool
    completion_method: Literal[
        "document_upload",
        "employee_signature",
        "employer_evidence",
        "manual_review",
    ]
    applicability_review_required: bool
    applicability_status: Literal["applied", "pending_review", "not_applicable"]
    retention_rule: str
    data_classification: Literal[
        "internal", "confidential", "restricted", "highly_restricted"
    ]
    data_category: Literal[
        "general", "identity_i9", "tax", "banking", "medical_disability", "veteran"
    ]
    official_source: str
    legal_review_status: Literal["pending", "approved"]
    signature_statement: str | None = None
    applicability_decided_at: datetime | None = None
    applicability_decided_by: str | None = None
    rule_version: str
    completed_at: datetime | None = None
    completed_by: str | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeDocumentSummary(BaseModel):
    id: UUID
    employee_id: UUID
    task_id: UUID
    version: int
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    data_classification: Literal["restricted", "highly_restricted"]
    status: Literal["active", "superseded"]
    uploaded_by: str
    created_at: datetime


class EmployeeTaskReview(BaseModel):
    decision: Literal["complete", "reject"]
    comment: str = Field(min_length=1, max_length=2_000)


class EmployeeTaskApplicabilityReview(BaseModel):
    decision: Literal["applicable", "not_applicable"]
    comment: str = Field(min_length=1, max_length=2_000)
    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_qualification: str = Field(min_length=1, max_length=300)
    legal_review_confirmed: Literal[True]


class EmployeeSignatureCreate(BaseModel):
    typed_name: str = Field(min_length=1, max_length=200)
    accepted: Literal[True]


class EmployeeSignatureSummary(BaseModel):
    id: UUID
    employee_id: UUID
    task_id: UUID
    version: int
    signer_email: EmailStr
    typed_name: str
    statement_version: str
    statement_hash: str
    status: Literal["active", "superseded"]
    signed_at: datetime


class ComplianceRequirement(BaseModel):
    id: str
    label: str
    responsible_party: Literal["employee", "employer", "contractor"]
    applicability: str
    retention_rule: str
    trigger: str
    task_owner: Literal["employee", "employer", "contractor"]
    completion_method: Literal[
        "document_upload",
        "employee_signature",
        "employer_evidence",
        "manual_review",
    ]
    data_classification: Literal[
        "internal", "confidential", "restricted", "highly_restricted"
    ]
    data_category: Literal[
        "general", "identity_i9", "tax", "banking", "medical_disability", "veteran"
    ]
    official_source: str
    legal_review_status: Literal["pending", "approved"] = "pending"


class OnboardingEmployeeSummary(EmployeeSummary):
    version: int = Field(ge=1)


class OnboardingTaskSummary(EmployeeTaskSummary):
    version: int = Field(ge=1)
    latest_rejection_reason: str | None = None


class EmployeeInviteCommand(BaseModel):
    expected_version: int = Field(ge=1)


class OnboardingInviteReceipt(BaseModel):
    id: UUID
    employee_id: UUID
    status: Literal["pending_delivery"] = "pending_delivery"
    expires_at: datetime
    version: int = Field(ge=1)


class VersionedTaskReview(BaseModel):
    expected_version: int = Field(ge=1)
    decision: Literal["complete", "reject"]
    comment: str = Field(min_length=1, max_length=2_000)


class VersionedApplicabilityReview(BaseModel):
    expected_version: int = Field(ge=1)
    decision: Literal["applicable", "not_applicable"]
    comment: str = Field(min_length=1, max_length=2_000)
    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_qualification: str = Field(min_length=1, max_length=300)
    legal_review_confirmed: Literal[True]


class VersionedSignatureCreate(BaseModel):
    expected_version: int = Field(ge=1)
    typed_name: str = Field(min_length=1, max_length=200)
    accepted: Literal[True]


class TaskReviewSummary(BaseModel):
    id: UUID
    employee_id: UUID
    task_id: UUID
    review_type: Literal["task_review", "applicability"]
    from_status: str
    to_status: str
    decision: str
    comment: str
    reviewer_email: EmailStr
    reviewer_name: str | None = None
    reviewer_qualification: str | None = None
    rule_version: str
    task_version: int
    created_at: datetime


class IdentityProvisioningRequest(BaseModel):
    employee_id: UUID
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=120)


class IdentityCommandMutation(BaseModel):
    expected_version: int = Field(ge=1)


class IdentityAdminConfirmation(IdentityCommandMutation):
    confirmed_no_paid_license: Literal[True]
    reason: str = Field(min_length=1, max_length=2_000)
    evidence_reference: str = Field(min_length=1, max_length=500)


class IdentityProvisioningSummary(BaseModel):
    id: UUID
    employee_id: UUID
    kind: Literal["create", "suspend"]
    status: Literal[
        "pending_approval",
        "approved",
        "executing",
        "verified",
        "admin_confirmation_required",
        "admin_confirmed",
        "failed",
        "manual_review_required",
        "suspended",
    ]
    version: int
    target_email: EmailStr
    target_org_unit: str
    external_user_id: str | None = None
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime


class OffboardingRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)
    directory_idempotency_key: str = Field(min_length=8, max_length=120)


class OffboardingReceipt(BaseModel):
    id: UUID
    employee_id: UUID
    status: Literal["inactive"] = "inactive"
    version: int
    directory_command_id: UUID | None = None
    session_revoked_at: datetime


class RetentionHoldCreate(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2_000)


class RetentionHoldRelease(BaseModel):
    expected_version: int = Field(ge=1)


class RetentionHoldSummary(BaseModel):
    id: UUID
    employee_id: UUID
    reason: str
    created_by: EmailStr
    created_at: datetime
    released_by: EmailStr | None = None
    released_at: datetime | None = None


class ContractorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    invite_delivery_email: EmailStr
    start_date: date
    work_location: str = Field(min_length=1, max_length=200)
