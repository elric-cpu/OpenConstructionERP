# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Pydantic schemas for the clash detection module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Review-workflow states a clash can move through.
CLASH_STATUSES = ("new", "active", "reviewed", "approved", "resolved", "ignored")
# A clash that still needs attention (drives the "open clashes" KPI).
OPEN_STATUSES = ("new", "active", "reviewed")


class ClashSelectionSet(BaseModel):
    """One side (A or B) of a Navisworks-style selection-set clash.

    A *set* is a filter over the project's own elements: every element
    whose ``element_type`` is in :attr:`element_types` **or** whose
    ``discipline`` is in :attr:`disciplines` belongs to the set (union —
    each chip the user adds widens it). Used only with
    ``mode="selection_sets"``: a pair is reported iff one element is in
    Set A and the other is in Set B (strictly cross, e.g. walls × pipes,
    no wall × wall noise).
    """

    disciplines: list[str] = Field(default_factory=list, max_length=200)
    element_types: list[str] = Field(default_factory=list, max_length=2000)

    @property
    def is_empty(self) -> bool:
        return not self.disciplines and not self.element_types


class ClashRunCreate(BaseModel):
    """‌⁠‍Configure + launch a clash run."""

    name: str | None = Field(default=None, max_length=255)
    model_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="BIM models to test. One = intra-model; many = federated.",
    )
    tolerance_m: float = Field(
        default=0.01, ge=0.0, le=10.0,
        description="Hard-clash interpenetration threshold in metres.",
    )
    clearance_m: float = Field(
        default=0.0, ge=0.0, le=50.0,
        description="Proximity threshold in metres (0 disables the soft pass).",
    )
    mode: str = Field(
        default="cross_discipline",
        description="cross_discipline | all | selected | selection_sets",
    )
    discipline_filter: list[list[str]] | None = Field(
        default=None,
        description="Optional allow-list of [discipline_a, discipline_b] pairs.",
    )
    set_a: ClashSelectionSet | None = Field(
        default=None,
        description="Selection Set A (mode=selection_sets) — e.g. all walls.",
    )
    set_b: ClashSelectionSet | None = Field(
        default=None,
        description="Selection Set B (mode=selection_sets) — e.g. all pipes.",
    )


class ClashCategoryItem(BaseModel):
    """One distinct element_type / discipline value with its element count."""

    value: str
    count: int


class ClashCategoriesResponse(BaseModel):
    """Facets for building the Set A / Set B pickers (one project)."""

    element_types: list[ClashCategoryItem] = Field(default_factory=list)
    disciplines: list[ClashCategoryItem] = Field(default_factory=list)


class ClashResultResponse(BaseModel):
    """‌⁠‍A single clashing pair."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    a_element_id: uuid.UUID
    b_element_id: uuid.UUID
    a_stable_id: str
    b_stable_id: str
    a_name: str
    b_name: str
    a_discipline: str
    b_discipline: str
    a_element_type: str = ""
    b_element_type: str = ""
    a_model_id: uuid.UUID
    b_model_id: uuid.UUID
    a_storey: int | None = None
    b_storey: int | None = None
    clash_type: str
    penetration_m: float
    distance_m: float
    cx: float
    cy: float
    cz: float
    status: str
    assigned_to: str | None
    bcf_topic_guid: str | None


class ClashResultUpdate(BaseModel):
    """Triage a clash — change its status and/or assignee."""

    status: str | None = Field(default=None)
    assigned_to: str | None = Field(default=None)


class ClashMatrixCell(BaseModel):
    """One discipline×discipline cell of the clash matrix."""

    a: str
    b: str
    count: int
    open_count: int


class ClashLevelMatrixCell(BaseModel):
    """One storey×storey cell of the level matrix.

    Same shape/convention as :class:`ClashMatrixCell` so the frontend can
    render it with the identical grid component — only the axis keys are
    integer storey indices instead of discipline strings.
    """

    a: int
    b: int
    count: int
    open_count: int


class ClashRunSummary(BaseModel):
    """Rendered dashboard payload cached on the run.

    ``matrix`` is the discipline×discipline grid (correct for true
    multi-discipline federated uploads). ``level_matrix`` is the
    storey×storey grid (the meaningful coordination view for the common
    single-discipline intra-model run). Both follow the same cell shape.
    """

    disciplines: list[str] = Field(default_factory=list)
    matrix: list[ClashMatrixCell] = Field(default_factory=list)
    storeys: list[int] = Field(default_factory=list)
    level_matrix: list[ClashLevelMatrixCell] = Field(default_factory=list)
    by_status: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)


class ClashRunResponse(BaseModel):
    """A clash run with its cached summary."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    model_ids: list[uuid.UUID]
    tolerance_m: float
    clearance_m: float
    mode: str
    discipline_filter: list[list[str]] | None
    set_a: ClashSelectionSet | None = None
    set_b: ClashSelectionSet | None = None
    status: str
    error: str | None
    element_count: int
    total_clashes: int
    summary: ClashRunSummary
    created_by: str
    created_at: datetime
    completed_at: datetime | None


class ClashRunListItem(BaseModel):
    """Lightweight run row for the runs list (no result rows)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    model_ids: list[uuid.UUID]
    element_count: int
    total_clashes: int
    created_at: datetime
    completed_at: datetime | None


class ClashResultPage(BaseModel):
    """Paginated clash-result slice."""

    items: list[ClashResultResponse]
    total: int
    offset: int
    limit: int


class ClashBCFExportRequest(BaseModel):
    """Export selected clashes (or all open) as native BCF topics."""

    result_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Specific clashes to export. Omit → all OPEN clashes.",
    )


class ClashBCFExportResponse(BaseModel):
    """Outcome of a BCF export."""

    exported: int
    skipped: int
