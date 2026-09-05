from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    organization: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    device_name: str | None = Field(default=None, max_length=300)


class TokenResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = 0
    csrf_token: str | None = None
    mfa_required: bool = False
    mfa_challenge_token: str | None = None


class RefreshRequest(BaseModel):
    csrf_token: str = Field(min_length=32, max_length=200)


class MfaVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=32)
    code: str = Field(min_length=6, max_length=32)
    device_name: str | None = Field(default=None, max_length=300)


class MfaEnrollment(BaseModel):
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class SessionRead(BaseModel):
    id: str
    device_name: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: str
    last_seen_at: str
    expires_at: str
    current: bool


class EmployeeActivationToken(BaseModel):
    token: str = Field(min_length=80, max_length=500)


class EmployeeActivationInspectRead(BaseModel):
    employee_name: str
    company_email: EmailStr
    organization_name: str
    expires_at: datetime


class EmployeeActivationComplete(EmployeeActivationToken):
    password: str = Field(min_length=12, max_length=1024)


class EmployeeActivationCompleteRead(BaseModel):
    activated: bool
    organization: str
    email: EmailStr
