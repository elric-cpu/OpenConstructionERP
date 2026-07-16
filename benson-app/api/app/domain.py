from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


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
        id="dashboard", label="Today", group="workspace", roles=FIELD_STAFF | FINANCE_STAFF
    ),
    ModuleDefinition(id="crm", label="Leads & CRM", group="sales", roles=STAFF),
    ModuleDefinition(
        id="contacts", label="Contacts", group="sales", roles=STAFF | {Role.ACCOUNTING}
    ),
    ModuleDefinition(id="estimates", label="Estimates", group="sales", roles=STAFF),
    ModuleDefinition(
        id="projects", label="Jobs", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF
    ),
    ModuleDefinition(id="schedule", label="Schedule", group="delivery", roles=FIELD_STAFF),
    ModuleDefinition(id="field", label="Field Notes", group="delivery", roles=FIELD_STAFF),
    ModuleDefinition(id="time", label="Time", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF),
    ModuleDefinition(
        id="documents",
        label="Documents",
        group="delivery",
        roles=FIELD_STAFF | FINANCE_STAFF | {Role.CUSTOMER},
    ),
    ModuleDefinition(
        id="procurement", label="Purchasing", group="operations", roles=STAFF | FINANCE_STAFF
    ),
    ModuleDefinition(
        id="subcontractors",
        label="Subcontractors",
        group="operations",
        roles=STAFF | FINANCE_STAFF | {Role.SUBCONTRACTOR},
    ),
    ModuleDefinition(id="inventory", label="Materials", group="operations", roles=FIELD_STAFF),
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
        id="portal", label="Customer Portal", group="portal", roles=STAFF | {Role.CUSTOMER}
    ),
    ModuleDefinition(
        id="agent", label="Operations Agent", group="intelligence", roles=STAFF | FINANCE_STAFF
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


class LeadUpdate(BaseModel):
    status: Literal["new", "contacted", "qualified", "scheduled", "closed"] | None = None
    assigned_to: EmailStr | None = None
    note: str | None = Field(default=None, min_length=1, max_length=5_000)


class NotificationSettingsUpdate(BaseModel):
    sms_enabled: bool


class NotificationSettings(BaseModel):
    email_enabled: Literal[True] = True
    sms_enabled: bool
    sms_configured: bool


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
