"""Pydantic schemas for the dashboard rollup endpoint.

Each widget has its own concrete shape so the OpenAPI doc is useful, but
the top-level response (``RollupResponse``) keys are dynamic — only the
widgets the caller asked for are populated. Unrequested widgets are
absent (not ``None``) so the frontend can use ``in`` to detect coverage.

All money fields ship as **strings**, never floats, per the architecture guide §10:
JS ``Number`` loses precision on currency values > 2^53, and ``orjson``
defaults can stringify-without-rounding nondeterministically.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Widget(BaseModel):
    """Common base — allow extra so we can extend payloads without re-shipping schemas."""

    model_config = ConfigDict(extra="allow")


class BOQByProject(BaseModel):
    project_id: str
    project_name: str
    boq_count: int
    total_value: str = Field(description="Decimal-as-string in project currency.")
    currency: str
    position_count: int
    positions_missing_quantity: int
    positions_zero_price: int


class LastBOQRef(BaseModel):
    """Most-recently-edited BOQ across the caller's projects.

    Powers the "Continue your work" tile + KpiRibbon active-estimates count
    without per-project ``/v1/boq/boqs/`` fan-out.
    """

    id: str
    name: str
    project_id: str
    project_name: str
    currency: str
    status: str | None
    updated_at: str
    position_count: int
    grand_total: str  # Decimal-as-string


class BOQSummaryPayload(_Widget):
    total_boqs: int
    active_boqs: int = Field(
        default=0,
        description=(
            "BOQs whose status is NOT in archived/closed/cancelled/rejected."
        ),
    )
    total_value_eur: str = Field(description="Sum across all projects, **EUR equivalent** as Decimal string.")
    position_count: int
    positions_missing_quantity: int
    positions_zero_price: int
    last_boq: LastBOQRef | None = None
    by_project: list[BOQByProject]


class ValidationByProject(BaseModel):
    project_id: str
    project_name: str
    avg_score: float | None
    passed: int
    warnings: int
    errors: int


class ValidationScorePayload(_Widget):
    avg: float | None = Field(description="Mean of latest-per-project scores (0.0-1.0), None when no reports.")
    passed: int
    warnings: int
    errors: int
    by_project: list[ValidationByProject]


class ClashByProject(BaseModel):
    project_id: str
    project_name: str
    total: int
    open: int
    high: int
    medium: int
    low: int


class ClashHealthPayload(_Widget):
    total: int
    open: int
    high: int
    medium: int
    low: int
    pct_resolved: int
    by_project: list[ClashByProject]


class CriticalTaskItem(BaseModel):
    id: str
    name: str
    project_id: str
    project_name: str
    start_date: str | None
    end_date: str | None
    status: str | None
    is_critical: bool
    total_float: int | None


class ScheduleCriticalPayload(_Widget):
    total_schedules: int = Field(
        default=0,
        description="Total schedule rows across the caller's accessible projects.",
    )
    top: list[CriticalTaskItem]


class RiskItem(BaseModel):
    id: str
    project_id: str
    project_name: str
    title: str
    score: float
    probability: float
    impact_severity: str
    status: str | None


class RiskTopPayload(_Widget):
    top: list[RiskItem]


class HSEByProject(BaseModel):
    project_id: str
    project_name: str
    total: int
    last_30d: int
    near_miss: int
    recordables: int
    days_since_last: int | None


class HSEScorecardPayload(_Widget):
    total: int
    last_30d: int
    near_miss: int
    recordables: int
    days_since_last: int | None
    by_project: list[HSEByProject]


class ProcurementPipelinePayload(_Widget):
    rfqs_pending: int
    pos_issued: int
    pos_received: int


class BudgetByProject(BaseModel):
    project_id: str
    project_name: str
    currency: str
    planned: str  # Decimal-as-string
    actual: str
    variance: str
    pct: int  # percent over (positive) / under (negative)


class BudgetVariancePayload(_Widget):
    over_budget_count: int
    top_over: list[BudgetByProject]


class ChangeOrderItem(BaseModel):
    id: str
    project_id: str
    project_name: str
    code: str | None
    title: str | None
    status: str | None
    cost_impact: str  # Decimal-as-string
    currency: str


class ChangeOrdersPayload(_Widget):
    open_count: int
    total_impact: str  # Decimal-as-string
    currency: str
    top_pending: list[ChangeOrderItem]


class WeatherSitePayload(_Widget):
    project_id: str | None
    project_name: str | None
    city: str | None
    temperature_c: float | None
    conditions: str | None
    source: str | None


class RollupResponse(BaseModel):
    """Top-level rollup response.

    Only requested widget keys are populated. Each value is the
    matching widget payload above (or omitted if the caller didn't
    request it / no data was available).
    """

    # We keep this as an open dict so widgets can be added without
    # touching the schema. OpenAPI doc references concrete payloads
    # for the typed widgets above so frontend type generation still
    # picks them up.
    model_config = ConfigDict(extra="allow")

    boq_summary: BOQSummaryPayload | None = None
    validation_score: ValidationScorePayload | None = None
    clash_health: ClashHealthPayload | None = None
    schedule_critical: ScheduleCriticalPayload | None = None
    risk_top: RiskTopPayload | None = None
    hse_scorecard: HSEScorecardPayload | None = None
    procurement_pipeline: ProcurementPipelinePayload | None = None
    budget_variance: BudgetVariancePayload | None = None
    change_orders: ChangeOrdersPayload | None = None
    weather_site: WeatherSitePayload | None = None

    # Cache metadata — populated by the router so the frontend can
    # display a "last refreshed Xs ago" stamp without round-tripping
    # headers through React Query's transport layer.
    generated_at: str = Field(description="ISO-8601 timestamp.")
    widgets_requested: list[str] = Field(default_factory=list)
    project_count: int = 0


__all__ = [
    "BOQByProject",
    "BOQSummaryPayload",
    "BudgetByProject",
    "BudgetVariancePayload",
    "ChangeOrderItem",
    "ChangeOrdersPayload",
    "ClashByProject",
    "ClashHealthPayload",
    "CriticalTaskItem",
    "HSEByProject",
    "HSEScorecardPayload",
    "LastBOQRef",
    "ProcurementPipelinePayload",
    "RiskItem",
    "RiskTopPayload",
    "RollupResponse",
    "ScheduleCriticalPayload",
    "ValidationByProject",
    "ValidationScorePayload",
    "WeatherSitePayload",
]
