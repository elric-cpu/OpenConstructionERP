import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.estimating.calculations import PricingMode
from app.modules.estimating.models import EstimateStatus, ProposalStatus


class EstimateCreate(BaseModel):
    lead_id: uuid.UUID
    pricing_mode: PricingMode
    pricing_rate: Decimal = Field(ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0)


class EstimateLineCreate(BaseModel):
    section_title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=30)
    unit_cost: Decimal = Field(ge=0)
    category: str = Field(pattern="^(LABOR|MATERIAL|EQUIPMENT|SUBCONTRACTOR|OTHER)$")
    position: int = Field(ge=0)
    expected_version: int = Field(ge=1)


class EstimateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    property_id: uuid.UUID
    status: EstimateStatus
    pricing_mode: PricingMode
    pricing_rate: Decimal
    direct_cost: Decimal
    selling_price: Decimal
    tax: Decimal
    total: Decimal
    version: int


class ProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estimate_id: uuid.UUID
    document_version: int
    status: ProposalStatus
    price_snapshot: dict
    document_id: uuid.UUID
    document_checksum: str | None = None
    version: int


class ProposalAccept(BaseModel):
    accepted_by_name: str = Field(min_length=1, max_length=200)
    consent: bool
    acceptance_statement: str = Field(min_length=20, max_length=1000)
    expected_version: int = Field(ge=1)


class ProposalDocumentAccess(BaseModel):
    url: str | None
    expires_at: datetime
    proxied: bool
