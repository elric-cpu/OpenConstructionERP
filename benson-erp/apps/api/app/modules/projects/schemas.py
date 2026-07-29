import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_number: str = Field(min_length=1, max_length=50)
    contract_number: str = Field(min_length=1, max_length=50)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    proposal_id: uuid.UUID
    contract_id: uuid.UUID
    customer_id: uuid.UUID
    property_id: uuid.UUID
    project_number: str
    name: str
    status: str


class ProjectCreationRead(BaseModel):
    project: ProjectRead
    contract_value: Decimal
    budget_line_count: int
