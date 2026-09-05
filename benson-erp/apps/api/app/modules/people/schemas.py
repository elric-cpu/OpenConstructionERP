import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.people.models import EmployeeStatus, IdentityProvisioningStatus


class EmployeeCreate(BaseModel):
    employee_number: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    personal_email: EmailStr
    company_username: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,78}[a-z0-9]$")
    hire_date: date
    manager_user_id: uuid.UUID | None = None
    google_org_unit_path: str | None = Field(default=None, max_length=500)

    @field_validator("employee_number", "first_name", "last_name", "company_username")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("company_username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class EmployeeApproval(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_number: str
    first_name: str
    last_name: str
    preferred_name: str | None
    personal_email: EmailStr
    company_username: str
    company_email: EmailStr | None
    hire_date: date
    manager_user_id: uuid.UUID | None
    status: EmployeeStatus
    google_subject_id: str | None
    google_org_unit_path: str | None
    approved_at: datetime | None
    identity_created_at: datetime | None
    activation_sent_at: datetime | None
    erp_access_confirmed_at: datetime | None
    version: int


class EmployeeActivationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    expires_at: datetime
    sent_at: datetime | None
    used_at: datetime | None
    revoked_at: datetime | None
    attempt_count: int
    last_attempt_at: datetime | None
    version: int


class EmployeeActivationReissue(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class EmployeeActivationPreview(BaseModel):
    activation_url: str
    expires_at: datetime


class IdentityProvisioningRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    status: IdentityProvisioningStatus
    primary_email: EmailStr
    external_user_id: str | None
    completed_at: datetime | None
    version: int


class EmployeeApprovalRead(BaseModel):
    employee: EmployeeRead
    provisioning: IdentityProvisioningRead
