from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field, model_validator


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    OFFICE = "office"
    ESTIMATOR_PM = "estimator_pm"
    FIELD = "field"
    ACCOUNTING = "accounting"
    SUBCONTRACTOR = "subcontractor"
    CUSTOMER = "customer"


class ModuleDefinition(BaseModel):
    id: str
    label: str
    group: str
    roles: set[Role]


STAFF = {Role.OWNER, Role.ADMIN, Role.OFFICE, Role.ESTIMATOR_PM}
FIELD_STAFF = STAFF | {Role.FIELD}
FINANCE_STAFF = {Role.OWNER, Role.ADMIN, Role.ACCOUNTING}

BENSON_MODULES = [
    ModuleDefinition(
        id="dashboard",
        label="Today",
        group="workspace",
        roles=FIELD_STAFF | FINANCE_STAFF,
    ),
    ModuleDefinition(id="crm", label="Leads & CRM", group="sales", roles=STAFF),
    ModuleDefinition(
        id="contacts", label="Contacts", group="sales", roles=STAFF | {Role.ACCOUNTING}
    ),
    ModuleDefinition(id="estimates", label="Estimates", group="sales", roles=STAFF),
    ModuleDefinition(
        id="projects", label="Jobs", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF
    ),
    ModuleDefinition(
        id="schedule", label="Schedule", group="delivery", roles=FIELD_STAFF
    ),
    ModuleDefinition(
        id="field", label="Field Notes", group="delivery", roles=FIELD_STAFF
    ),
    ModuleDefinition(
        id="time", label="Time", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF
    ),
    ModuleDefinition(
        id="documents",
        label="Documents",
        group="delivery",
        roles=FIELD_STAFF | FINANCE_STAFF | {Role.CUSTOMER},
    ),
    ModuleDefinition(
        id="procurement",
        label="Purchasing",
        group="operations",
        roles=STAFF | FINANCE_STAFF,
    ),
    ModuleDefinition(
        id="subcontractors",
        label="Subcontractors",
        group="operations",
        roles=STAFF | FINANCE_STAFF | {Role.SUBCONTRACTOR},
    ),
    ModuleDefinition(
        id="inventory", label="Materials", group="operations", roles=FIELD_STAFF
    ),
    ModuleDefinition(
        id="quality",
        label="Quality & Punch",
        group="operations",
        roles=FIELD_STAFF | {Role.CUSTOMER},
    ),
    ModuleDefinition(
        id="service",
        label="Service & Warranty",
        group="operations",
        roles=FIELD_STAFF | {Role.CUSTOMER},
    ),
    ModuleDefinition(
        id="finance", label="Job Cost & Billing", group="finance", roles=FINANCE_STAFF
    ),
    ModuleDefinition(
        id="accounting", label="Accounting Sync", group="finance", roles=FINANCE_STAFF
    ),
    ModuleDefinition(
        id="portal",
        label="Customer Portal",
        group="portal",
        roles=STAFF | {Role.CUSTOMER},
    ),
    ModuleDefinition(
        id="agent",
        label="Operations Agent",
        group="intelligence",
        roles=STAFF | FINANCE_STAFF,
    ),
    ModuleDefinition(
        id="audit", label="Audit Trail", group="admin", roles={Role.OWNER, Role.ADMIN}
    ),
]


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=7, max_length=40)
    email: EmailStr | None = None
    preferred_contact: Literal["phone", "email", "text", ""] = ""
    customer_type: str = Field(default="homeowner", max_length=80)
    address: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=120)
    zip_code: str = Field(default="", pattern=r"^$|^\d{5}$")
    service_type: str = Field(min_length=1, max_length=120)
    urgency: Literal["standard", "soon", "emergency"] = "standard"
    item_count: str = Field(default="", max_length=300)
    dimensions: str = Field(default="", max_length=500)
    access_notes: str = Field(default="", max_length=1_000)
    timeline: str = Field(default="", max_length=300)
    message: str = Field(min_length=1, max_length=10_000)
    form_context: str = Field(default="general", max_length=200)
    source_page: str = Field(default="", max_length=500)
    utm_source: str = Field(default="", max_length=200)
    utm_medium: str = Field(default="", max_length=200)
    utm_campaign: str = Field(default="", max_length=200)
    referrer: str = Field(default="", max_length=1_000)
    consent_to_contact: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class LeadIntake(BaseModel):
    contact_name: str = Field(min_length=1, max_length=200)
    contact_phone: str = Field(min_length=7, max_length=40)
    contact_email: EmailStr | None = None
    source: Literal["web"] = "web"
    webhook_source: Literal["benson-website"] = "benson-website"
    workflow: Literal["website-lead-intake"] = "website-lead-intake"
    status: Literal["new"] = "new"
    qualification_notes: str = Field(min_length=1, max_length=10_000)
    contact: dict[str, str] = Field(default_factory=dict)
    project: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_canonical(self) -> LeadCreate:
        metadata = self.metadata
        return LeadCreate(
            name=self.contact_name,
            phone=self.contact_phone,
            email=self.contact_email,
            customer_type=str(metadata.get("customerType", "homeowner")),
            address=str(metadata.get("address", "")),
            city=str(metadata.get("city", "")),
            zip_code=str(metadata.get("zip", "")),
            service_type=str(self.project.get("serviceType", "general-construction")),
            urgency=str(self.project.get("urgency", "standard")),
            item_count=str(metadata.get("itemCount", "")),
            dimensions=str(metadata.get("dimensions", "")),
            access_notes=str(metadata.get("accessNotes", "")),
            timeline=str(metadata.get("timeline", "")),
            message=str(self.project.get("notes", self.qualification_notes)),
            form_context=str(metadata.get("formContext", "legacy")),
            source_page=str(metadata.get("sourcePage", "")),
            metadata={"legacy_payload": True},
        )


class LeadReceipt(BaseModel):
    lead_id: UUID
    status: Literal["accepted"] = "accepted"
    upload_session_id: UUID
    upload_url: str
    accepted_at: datetime
    duplicate: bool = False


class LeadSummary(BaseModel):
    id: UUID
    status: str
    priority: str
    name: str
    phone: str
    email: str | None
    service_type: str
    city: str
    created_at: datetime
    assigned_to: str | None = None
    source: str
    is_spam: bool = False
    spam_reason: str | None = None


class LeadUpdate(BaseModel):
    status: Literal["new", "contacted", "qualified", "scheduled", "closed"] | None = (
        None
    )
    assigned_to: EmailStr | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=7, max_length=40)
    email: EmailStr | None = None
    service_type: str | None = Field(default=None, min_length=1, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, min_length=1, max_length=200)
    is_spam: bool | None = None


class NotificationSettingsUpdate(BaseModel):
    sms_enabled: bool


class NotificationSettings(BaseModel):
    email_enabled: Literal[True] = True
    sms_enabled: bool
    sms_configured: bool


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    phone: str = Field(min_length=7, max_length=40)
    email: EmailStr | None = None
    billing_address: str = Field(default="", max_length=500)
    service_address: str = Field(default="", max_length=500)
    city: str = Field(default="", max_length=120)
    state: str = Field(default="OR", min_length=2, max_length=2)
    zip_code: str = Field(default="", pattern=r"^$|^\d{5}$")
    notes: str = Field(default="", max_length=5_000)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, min_length=7, max_length=40)
    email: EmailStr | None = None
    billing_address: str | None = Field(default=None, max_length=500)
    service_address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    zip_code: str | None = Field(default=None, pattern=r"^$|^\d{5}$")
    notes: str | None = Field(default=None, max_length=5_000)


class CustomerSummary(CustomerCreate):
    id: UUID
    status: Literal["active", "archived"]
    source_lead_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class EstimateLineInput(BaseModel):
    description: str = Field(min_length=1, max_length=1_000)
    quantity: Decimal = Field(gt=0, le=1_000_000, max_digits=12, decimal_places=2)
    unit: str = Field(default="each", min_length=1, max_length=40)
    unit_price_cents: int = Field(ge=0, le=100_000_000)


class EstimateCreate(BaseModel):
    customer_id: UUID
    title: str = Field(min_length=1, max_length=300)
    scope_notes: str = Field(default="", max_length=10_000)
    valid_until: date
    lines: list[EstimateLineInput] = Field(min_length=1, max_length=200)


class EstimateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    scope_notes: str | None = Field(default=None, max_length=10_000)
    valid_until: date | None = None
    lines: list[EstimateLineInput] | None = Field(
        default=None, min_length=1, max_length=200
    )


class EstimateTransition(BaseModel):
    status: Literal["draft", "ready", "sent", "accepted", "declined", "void"]
    external_delivery_confirmed: bool = False
    note: str = Field(default="", max_length=2_000)


class EstimateLineSummary(EstimateLineInput):
    id: UUID
    position: int
    line_total_cents: int


class EstimateSummary(BaseModel):
    id: UUID
    number: str
    customer_id: UUID
    customer_name: str
    title: str
    scope_notes: str
    valid_until: date
    status: Literal["draft", "ready", "sent", "accepted", "declined", "void"]
    version: int
    subtotal_cents: int
    total_cents: int
    lines: list[EstimateLineSummary]
    created_at: datetime
    updated_at: datetime


ESTIMATE_TRANSITIONS = {
    "draft": {"ready", "void"},
    "ready": {"draft", "sent", "void"},
    "sent": {"accepted", "declined", "void"},
    "accepted": set(),
    "declined": set(),
    "void": set(),
}


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    invite_delivery_email: EmailStr | None = None
    workspace_unlicensed_confirmed: bool = False
    start_date: date
    work_location: str = Field(min_length=1, max_length=200)
    classification: Literal["employee", "independent_contractor"]
    role: Role
    federal_contract_applicability: Literal[
        "unknown", "not_applicable", "applicable"
    ] = "unknown"

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
    official_source: str
    legal_review_status: Literal["pending", "approved"] = "pending"


class AgentRunRequest(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=20_000)
    lead_id: UUID


class AgentActionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    role: Role
    tools: list[str] = Field(default_factory=list, max_length=20)
    record_context: dict[str, Any] = Field(default_factory=dict)


class AgentActionResult(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    status: Literal["completed", "confirmation_required", "failed"]
    summary: str
    proposed_actions: list[dict[str, Any]] = Field(default_factory=list)
    model: str
    audited_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProposalDecision(BaseModel):
    comment: str = Field(default="", max_length=2_000)
