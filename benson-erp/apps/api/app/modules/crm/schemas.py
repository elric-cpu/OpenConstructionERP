import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.crm.models import LeadStatus


class LeadCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    source: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=10_000)


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: LeadStatus
    customer_id: uuid.UUID | None
    property_id: uuid.UUID | None
    version: int


class LeadQualify(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=1)


class PropertyInput(BaseModel):
    address_line_1: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=5, max_length=10)


class LeadConvert(BaseModel):
    property: PropertyInput
    expected_version: int = Field(ge=1)


class ConversionRead(BaseModel):
    lead_id: uuid.UUID
    customer_id: uuid.UUID
    property_id: uuid.UUID
