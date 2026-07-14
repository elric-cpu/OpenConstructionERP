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
    ModuleDefinition(id="dashboard", label="Today", group="workspace", roles=FIELD_STAFF | FINANCE_STAFF),
    ModuleDefinition(id="crm", label="Leads & CRM", group="sales", roles=STAFF),
    ModuleDefinition(id="contacts", label="Contacts", group="sales", roles=STAFF | {Role.ACCOUNTING}),
    ModuleDefinition(id="estimates", label="Estimates", group="sales", roles=STAFF),
    ModuleDefinition(id="projects", label="Jobs", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF),
    ModuleDefinition(id="schedule", label="Schedule", group="delivery", roles=FIELD_STAFF),
    ModuleDefinition(id="field", label="Field Notes", group="delivery", roles=FIELD_STAFF),
    ModuleDefinition(id="time", label="Time & Payroll Prep", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF),
    ModuleDefinition(id="documents", label="Documents", group="delivery", roles=FIELD_STAFF | FINANCE_STAFF | {Role.CUSTOMER}),
    ModuleDefinition(id="procurement", label="Purchasing", group="operations", roles=STAFF | FINANCE_STAFF),
    ModuleDefinition(id="subcontractors", label="Subcontractors", group="operations", roles=STAFF | FINANCE_STAFF | {Role.SUBCONTRACTOR}),
    ModuleDefinition(id="inventory", label="Materials", group="operations", roles=FIELD_STAFF),
    ModuleDefinition(id="equipment", label="Equipment", group="operations", roles=FIELD_STAFF),
    ModuleDefinition(id="quality", label="Quality & Punch", group="operations", roles=FIELD_STAFF | {Role.CUSTOMER}),
    ModuleDefinition(id="safety", label="Safety", group="operations", roles=FIELD_STAFF),
    ModuleDefinition(id="service", label="Maintenance & Service", group="operations", roles=FIELD_STAFF | {Role.CUSTOMER}),
    ModuleDefinition(id="finance", label="Job Cost & Billing", group="finance", roles=FINANCE_STAFF),
    ModuleDefinition(id="quickbooks", label="QuickBooks Sync", group="finance", roles=FINANCE_STAFF),
    ModuleDefinition(id="portal", label="Customer Portal", group="portal", roles=STAFF | {Role.CUSTOMER}),
    ModuleDefinition(id="agent", label="Operations Agent", group="intelligence", roles=STAFF | FINANCE_STAFF),
    ModuleDefinition(id="audit", label="Audit Trail", group="admin", roles={Role.OWNER, Role.ADMIN}),
]


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


class LeadReceipt(BaseModel):
    lead_id: UUID = Field(default_factory=uuid4)
    status: Literal["accepted"] = "accepted"
    upload_session_id: UUID = Field(default_factory=uuid4)
    upload_url: str
    accepted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
