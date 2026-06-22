# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Construction-control Pydantic schemas - request/response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Shared regex fragments for the discriminators (kept here so router, service and
# tests reference one source of truth).
INSPECTION_TYPE_PATTERN = r"^(mir|wir|ir|hidden_works|acceptance)$"
PARTY_ROLE_PATTERN = r"^(qc|qa|tpi|ahj)$"
INTERVENTION_POINT_PATTERN = r"^(hold|witness|surveillance|review)$"
ACCEPTANCE_RULE_PATTERN = r"^(range|min|max|boolean|text)$"
RESULT_PATTERN = r"^(pass|fail|conditional)$"


# ── Universal Element Reference (UER) ─────────────────────────────────────────


class ElementRefIn(BaseModel):
    """Inbound element link. Any subset is accepted; the resolver fills the rest.

    A caller may pass the strong ``bim_element_id``, or the normalised
    ``(model_id, stable_id)``, or ``(model_id, native_id)``, or only denormalised
    display fields when the model is not yet ingested. IFC GlobalId is optional.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    bim_element_id: UUID | None = None
    model_id: UUID | None = None
    stable_id: str | None = Field(default=None, max_length=255)
    source_format: str | None = Field(default=None, max_length=20)
    ifc_global_id: str | None = Field(default=None, max_length=22)
    native_id: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=20)
    element_name: str | None = Field(default=None, max_length=500)
    element_type: str | None = Field(default=None, max_length=100)
    bbox: dict[str, Any] | None = None
    viewpoint: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ElementRefResponse(BaseModel):
    """A resolved UER as returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    owner_type: str
    owner_id: str
    project_id: UUID
    bim_element_id: UUID | None = None
    model_id: UUID | None = None
    stable_id: str | None = None
    source_format: str | None = None
    ifc_global_id: str | None = None
    native_id: str | None = None
    model_version: str | None = None
    element_name: str | None = None
    element_type: str | None = None
    bbox: dict[str, Any] | None = None
    viewpoint: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Acceptance criterion ──────────────────────────────────────────────────────


class AcceptanceCriterionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    code: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    standard_ref: str | None = Field(default=None, max_length=120)
    discipline: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=80)
    characteristic: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default=None, max_length=10000)
    unit: str | None = Field(default=None, max_length=40)
    acceptance_rule: str = Field(default="text", pattern=ACCEPTANCE_RULE_PATTERN)
    nominal_value: str | None = Field(default=None, max_length=80)
    tolerance_lower: str | None = Field(default=None, max_length=80)
    tolerance_upper: str | None = Field(default=None, max_length=80)
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcceptanceCriterionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    standard_ref: str | None = Field(default=None, max_length=120)
    discipline: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=80)
    characteristic: str | None = Field(default=None, max_length=255)
    method: str | None = Field(default=None, max_length=10000)
    unit: str | None = Field(default=None, max_length=40)
    acceptance_rule: str | None = Field(default=None, pattern=ACCEPTANCE_RULE_PATTERN)
    nominal_value: str | None = Field(default=None, max_length=80)
    tolerance_lower: str | None = Field(default=None, max_length=80)
    tolerance_upper: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class AcceptanceCriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    code: str
    title: str
    description: str | None = None
    standard_ref: str | None = None
    discipline: str | None = None
    category: str | None = None
    characteristic: str | None = None
    method: str | None = None
    unit: str | None = None
    acceptance_rule: str = "text"
    nominal_value: str | None = None
    tolerance_lower: str | None = None
    tolerance_upper: str | None = None
    is_active: bool = True
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


# ── Inspection ────────────────────────────────────────────────────────────────


class InspectionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    inspection_type: str = Field(..., pattern=INSPECTION_TYPE_PATTERN)
    party_role: str = Field(default="qc", pattern=PARTY_ROLE_PATTERN)
    intervention_point: str | None = Field(default=None, pattern=INTERVENTION_POINT_PATTERN)
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    location_description: str | None = Field(default=None, max_length=500)
    activity_id: str | None = Field(default=None, max_length=36)
    criterion_id: UUID | None = None
    scheduled_at: str | None = Field(default=None, max_length=40)
    # Optional element under inspection (the UER). When omitted the inspection is
    # not model-linked, which is valid for purely location-based checks.
    element: ElementRefIn | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InspectionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    inspection_type: str | None = Field(default=None, pattern=INSPECTION_TYPE_PATTERN)
    party_role: str | None = Field(default=None, pattern=PARTY_ROLE_PATTERN)
    intervention_point: str | None = Field(default=None, pattern=INTERVENTION_POINT_PATTERN)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    location_description: str | None = Field(default=None, max_length=500)
    activity_id: str | None = Field(default=None, max_length=36)
    criterion_id: UUID | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|scheduled|in_progress|passed|failed|closed|void)$")
    scheduled_at: str | None = Field(default=None, max_length=40)
    metadata: dict[str, Any] | None = None


class InspectionResultIn(BaseModel):
    """Record the outcome of an inspection. A ``fail`` (or ``conditional``) raises an NCR."""

    model_config = ConfigDict(str_strip_whitespace=True)

    result: str = Field(..., pattern=RESULT_PATTERN)
    measured_value: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=10000)
    performed_at: str | None = Field(default=None, max_length=40)
    # Severity used for an auto-raised NCR; defaults are derived from the result.
    ncr_severity: str | None = Field(default=None, pattern=r"^(critical|major|minor|observation)$")


class InspectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    inspection_number: str
    inspection_type: str
    party_role: str = "qc"
    intervention_point: str | None = None
    title: str
    description: str | None = None
    location_description: str | None = None
    activity_id: str | None = None
    criterion_id: str | None = None
    status: str = "draft"
    result: str | None = None
    measured_value: str | None = None
    result_notes: str | None = None
    raised_ncr_id: str | None = None
    scheduled_at: str | None = None
    performed_at: str | None = None
    performed_by: str | None = None
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
    # Resolved element links (populated by the service, not from_attributes).
    elements: list[ElementRefResponse] = Field(default_factory=list)
