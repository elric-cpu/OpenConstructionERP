# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the match-elements REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.match_service.config import DEFAULT_AUTO_CONFIRM_THRESHOLD
from app.core.match_service.envelope import MatchCandidate

SourceName = Literal["bim", "dwg", "boq", "text", "pdf", "photo", "image"]

# Per MAPPING_PROCESS.md v3 §4.2 the 12 OmniClass-aligned construction
# stages. These pin the SearchPlan ``construction_stage`` hard filter
# when the user explicitly picks a phase from the UI dropdown.
ConstructionStage = Literal[
    "02_Demolition",
    "03_Earthwork",
    "04_Foundations",
    "05_Substructure",
    "06_Superstructure",
    "07_Envelope",
    "08_Interior",
    "09_MEP",
    "10_Finishes",
    "11_FixedFurnishings",
    "12_Equipment",
    "13_Sitework",
]
GroupStatus = Literal[
    "unmatched",
    "suggested",
    "confirmed",
    "overridden",
    "skipped",
    "tbd",
    "applied",
]
TradeBucket = Literal[
    "architectural",
    "structural",
    "mep",
    "civil",
    "spatial",
    "subtractive",
    "annotation",
    "other",
]


class SessionCreate(BaseModel):
    project_id: uuid.UUID
    bim_model_id: uuid.UUID | None = None
    source: SourceName = "bim"
    name: str | None = None
    group_by: list[str] = Field(default_factory=list)
    filters: dict[str, list[Any]] = Field(default_factory=dict)
    # NULL = use the default subtractive set (IfcOpeningElement, etc.).
    # Pass [] explicitly to opt into showing voids/annotations.
    excluded_categories: list[str] | None = None
    auto_confirm_threshold: float = Field(
        default=DEFAULT_AUTO_CONFIRM_THRESHOLD, ge=0.0, le=1.0
    )
    use_net_quantities: bool = True
    catalogue_id: uuid.UUID | None = None
    construction_stage: ConstructionStage | None = None
    # MAPPING_PROCESS.md §4.1.6 — free-form text inputs for the "text"
    # source. List of strings (simple) or per-line dicts
    # ``{raw_text, project_country?, stage?, category?}``. Persisted on
    # ``MatchSession.metadata_["text_inputs"]`` and read back by
    # :class:`TextAdapter`. Ignored when ``source != "text"``.
    text_inputs: list[Any] | None = None
    # MAPPING_PROCESS.md §4.1.5 — pre-parsed BoQ rows for the "boq"
    # source. Each dict must have ``description``; recognised keys:
    # ``qty/quantity``, ``unit/uom``, ``code/rate_code`` (exact-match
    # shortcut), ``category/section``, ``source_lang``. Persisted on
    # ``MatchSession.metadata_["boq_rows"]`` and read back by
    # :class:`BoqAdapter`. Ignored when ``source != "boq"``.
    boq_rows: list[dict[str, Any]] | None = None
    # MAPPING_PROCESS.md §3.1 / §4.1.4 — image source binding. Either
    # ``{"path": "<abs>", "mime": "image/jpeg", "filename"?: "..."}``
    # for a file already on the storage backend, or
    # ``{"data_b64": "<base64>", "mime": "image/png", "filename"?: "..."}``
    # for an inline payload. ``image_id`` (any opaque string) is
    # forwarded verbatim into ``SourceElement.raw_ref`` so the UI can
    # link results back to the originating upload. Ignored when
    # ``source != "image"``.
    image: dict[str, Any] | None = None


class SessionUpdate(BaseModel):
    name: str | None = None
    bim_model_id: uuid.UUID | None = None
    group_by: list[str] | None = None
    filters: dict[str, list[Any]] | None = None
    excluded_categories: list[str] | None = None
    auto_confirm_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    use_net_quantities: bool | None = None
    catalogue_id: uuid.UUID | None = None
    is_archived: bool | None = None
    construction_stage: ConstructionStage | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    bim_model_id: uuid.UUID | None = None
    source: SourceName
    name: str | None
    group_by: list[str]
    filters: dict[str, list[Any]]
    excluded_categories: list[str]
    # Returned as a float so the UI never has to parse a string back.
    auto_confirm_threshold: float
    use_net_quantities: bool
    catalogue_id: uuid.UUID | None
    is_archived: bool = False
    construction_stage: ConstructionStage | None = None
    last_active_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SessionSummary(BaseModel):
    """Compact session row for the resume picker."""

    id: uuid.UUID
    project_id: uuid.UUID
    bim_model_id: uuid.UUID | None
    name: str | None
    source: SourceName
    last_active_at: datetime | None
    created_at: datetime
    is_archived: bool
    group_count: int
    confirmed_count: int
    applied_count: int
    total_value: float
    currency: str | None


class GroupSummary(BaseModel):
    """One row in the group grid — summary fields only."""

    id: uuid.UUID
    group_key: str
    # Server-translated, human-readable label for the row.
    # e.g. "Wall · Concrete C30/37 · 200mm · Level 1" rather than
    # the raw "ifc_class:IfcWallStandardCase|material:Concrete C30/37"
    # pipe-string.
    display_label: str = ""
    # Trade bucket (architectural / structural / MEP / civil / ...)
    # so the UI can colour-code or filter without re-deriving.
    trade: TradeBucket = "other"
    # True for IfcOpeningElement-style groups so the UI marks them
    # with a "void" badge — useful when the user toggles them on.
    is_subtractive: bool = False
    signature: str | None
    element_count: int
    quantities: dict[str, float]
    chosen_unit: str | None
    primary_quantity: float = 0.0
    # Gross/net pair; opening_warning fires when the host has openings
    # in IFC but gross == net, indicating the upstream IFC export bug
    # the user should know about (see Autodesk revit-ifc #496/#742).
    gross_quantity: float | None = None
    net_quantity: float | None = None
    opening_warning: bool = False
    chosen_method: str | None
    confidence: str | None
    confidence_band: Literal["high", "medium", "low", "none"] = "none"
    status: GroupStatus
    boq_position_id: uuid.UUID | None
    # Suggested cost item (top candidate's code+description) so the
    # UI can show what the row would map to without opening the panel.
    suggested_code: str | None = None
    suggested_description: str | None = None
    suggested_unit_rate: float | None = None
    suggested_currency: str | None = None
    sample_names: list[str] = Field(default_factory=list)


class GroupDetail(BaseModel):
    """Full detail for the slide-over panel."""

    id: uuid.UUID
    session_id: uuid.UUID
    group_key: str
    display_label: str = ""
    trade: TradeBucket = "other"
    is_subtractive: bool = False
    signature: str | None
    element_ids: list[str]
    element_count: int
    quantities: dict[str, float]
    chosen_unit: str | None
    gross_quantity: float | None = None
    net_quantity: float | None = None
    opening_warning: bool = False
    methods: dict[str, list[MatchCandidate]]
    chosen_candidate_id: uuid.UUID | None
    chosen_method: str | None
    confidence: str | None
    confidence_band: Literal["high", "medium", "low", "none"] = "none"
    status: GroupStatus
    boq_position_id: uuid.UUID | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    notes: str | None


class GroupListResponse(BaseModel):
    session_id: uuid.UUID
    total: int
    groups: list[GroupSummary]
    summary: dict[str, int]  # {"unmatched": 47, "suggested": 12, ...}
    # Confidence-band thresholds the matchers use, exposed to the UI so
    # frontend doesn't replicate the magic numbers in JS.
    confidence_high_threshold: float
    confidence_medium_threshold: float


class GroupSplitRequest(BaseModel):
    new_group_key: str
    element_ids: list[str]


class GroupMergeRequest(BaseModel):
    other_group_key: str
    new_group_key: str | None = None


class GroupOverride(BaseModel):
    chosen_unit: str | None = None
    notes: str | None = None


class RunMatchRequest(BaseModel):
    method: Literal["vector", "lexical", "resources", "llm"]
    group_keys: list[str] | None = None
    # Cap how many groups a single match call processes when no
    # group_keys are passed. Vector search over hundreds of groups
    # blocks the UI for minutes; default picks the N largest groups
    # by element_count so the user gets actionable matches in seconds.
    max_groups: int = Field(default=10, ge=1, le=200)
    top_k: int = Field(default=10, ge=1, le=50)


class ConfirmMatchRequest(BaseModel):
    group_key: str
    # Real CostItem.id (or CatalogResource.id when method=resources).
    # None means the user is confirming the group as a "manual override"
    # — a custom rate/description posted alongside.
    candidate_id: uuid.UUID | None = None
    method: Literal["vector", "lexical", "llm", "manual", "auto"] = "manual"
    confidence: float | None = None
    signature_fields_override: list[str] | None = None
    save_to_template_library: bool = True


class BulkConfirmRequest(BaseModel):
    threshold: float = Field(default=DEFAULT_AUTO_CONFIRM_THRESHOLD, ge=0.0, le=1.0)
    group_keys: list[str] | None = None  # None = all suggested


class ApplyToBoqRequest(BaseModel):
    dry_run: bool = False
    target_boq_id: uuid.UUID | None = None  # None = project's primary BOQ
    organize_by_classification: bool = True  # auto-DIN276 hierarchy preview
    group_keys: list[str] | None = None  # None = all confirmed


class ApplyResourcePreview(BaseModel):
    description: str
    factor: float  # per unit of parent position
    quantity: float  # factor × parent quantity
    unit: str
    unit_rate: float


class ApplyPositionPreview(BaseModel):
    group_key: str
    section_path: list[str]  # e.g. ["300 Konstruktionen", "330 Wände"]
    description: str
    unit: str
    quantity: float
    unit_rate: float
    currency: str
    line_total: float = 0.0
    resources: list[ApplyResourcePreview] = Field(default_factory=list)


class ApplyToBoqResponse(BaseModel):
    dry_run: bool
    boq_id: uuid.UUID | None
    positions_created: int
    positions: list[ApplyPositionPreview]
    grand_total: float = 0.0
    currency: str | None = None


class NoMatchRequest(BaseModel):
    group_key: str
    action: Literal["custom", "rfq", "tbd"]
    # When action=custom:
    custom_description: str | None = None
    custom_unit: str | None = None
    custom_rate: float | None = None
    save_to_my_catalogue: bool = False
    # When action=rfq:
    rfq_supplier_ids: list[uuid.UUID] | None = None


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    signature: str
    label: str | None
    cwicr_position_id: uuid.UUID
    source_fields: list[str]
    use_count: int
    last_used_at: datetime | None
    created_at: datetime


class TemplateLookupRequest(BaseModel):
    signatures: list[str]


class TemplateLookupResponse(BaseModel):
    matches: dict[str, TemplateRead]  # signature → template


class AttributeKey(BaseModel):
    """One drag-source chip in the group-by sidepanel."""
    key: str
    sample_values: list[str] = Field(default_factory=list)


class CategoryCount(BaseModel):
    category: str
    # Translated human label (from ifc_labels table).
    display_label: str = ""
    trade: TradeBucket = "other"
    is_subtractive: bool = False
    count: int


class BIMModelOption(BaseModel):
    """One BIM model offered for session binding in the BIM tab strip."""

    id: uuid.UUID
    name: str
    model_format: str | None
    element_count: int
    storey_count: int
    status: str
    created_at: datetime | None
