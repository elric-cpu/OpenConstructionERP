# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic response schemas for the change-intelligence API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PartyLoadOut(BaseModel):
    """Open-change load for one responsible party (ball in court)."""

    model_config = ConfigDict(from_attributes=True)

    party: str
    open_count: int
    overdue_count: int
    oldest_age_days: float
    total_age_days: float
    avg_age_days: float


class ItemAgingOut(BaseModel):
    """One open change record with its aging."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    code: str
    title: str
    status: str
    party: str
    age_days: float
    stale_days: float | None
    response_due_date: str | None
    overdue: bool
    days_to_due: float | None


class CycleTimeBoardOut(BaseModel):
    """The "waiting on whom" board for a project's open changes."""

    project_id: str
    as_of: datetime
    total_open: int
    total_overdue: int
    unassigned_open: int
    parties: list[PartyLoadOut]
    items: list[ItemAgingOut]


# --- Approved-change impact projection -------------------------------------
# Money is carried as a string (the Decimal rendered losslessly) per the
# platform money-as-string convention, so these are built explicitly in the
# router rather than validated straight off the engine dataclasses.


class KindImpactOut(BaseModel):
    """Committed cost and schedule carried by one kind of change."""

    kind: str
    count: int
    total_cost: str
    total_days: int


class CurrencyImpactOut(BaseModel):
    """Signed committed cost total in one currency."""

    currency: str
    total_cost: str
    count: int


class ImpactProjectionOut(BaseModel):
    """Earned-value-style roll-up of a project's approved changes."""

    project_id: str
    approved_count: int
    total_schedule_delta_days: int
    primary_currency: str
    primary_currency_cost: str
    by_kind: list[KindImpactOut]
    by_currency: list[CurrencyImpactOut]


# --- Change-request clarifier ----------------------------------------------


class ClarifyIn(BaseModel):
    """Request body for the clarifier: a rough change note to structure."""

    note: str
    contract_standard: str = ""


class ClarificationGapOut(BaseModel):
    """One thing still missing before a change request is fit to circulate."""

    model_config = ConfigDict(from_attributes=True)

    field: str
    question: str
    severity: str


class ClauseSuggestionOut(BaseModel):
    """A likely governing contract provision for the change."""

    model_config = ConfigDict(from_attributes=True)

    standard: str
    clause_ref: str
    rationale: str


class ClarifiedRequestOut(BaseModel):
    """A structured first draft of a change request built from a rough note."""

    model_config = ConfigDict(from_attributes=True)

    title: str
    normalized_summary: str
    detected_classification: str
    missing: list[ClarificationGapOut]
    clause_suggestions: list[ClauseSuggestionOut]
    suggested_route: str
    completeness: float


# --- Action coordination co-pilot ------------------------------------------


class CoordinationStepOut(BaseModel):
    """One ranked open item with its urgency and recommended next action."""

    model_config = ConfigDict(from_attributes=True)

    ref_id: str
    kind: str
    title: str
    ball_in_court: str
    urgency: str
    days_to_due: int | None
    recommended_action: str
    reason: str
    rank_score: int


class CoordinationPlanOut(BaseModel):
    """The "what to act on first" plan over a project's open change items."""

    project_id: str
    generated_at: str
    total: int
    overdue_count: int
    due_soon_count: int
    steps: list[CoordinationStepOut]


# --- Correspondence consolidator co-pilot ----------------------------------


class ThreadDigestOut(BaseModel):
    """Consolidated state of one correspondence thread."""

    model_config = ConfigDict(from_attributes=True)

    thread_key: str
    subject: str
    message_count: int
    participants: list[str]
    first_at: str | None
    last_at: str | None
    last_direction: str
    last_sender: str
    awaiting: str
    is_open: bool


class CommsDigestOut(BaseModel):
    """Project-wide roll-up of correspondence threads and who owes a reply."""

    project_id: str
    generated_at: str
    thread_count: int
    open_count: int
    awaiting_us_count: int
    threads: list[ThreadDigestOut]


# --- Ownership hand-off chain ----------------------------------------------


class OwnershipSegmentOut(BaseModel):
    """One uninterrupted stretch during which a party held the ball."""

    party: str | None
    from_ts: str
    to_ts: str | None
    dwell_days: float
    is_open: bool
    set_by: str | None
    reason: str | None


class PartyDwellOut(BaseModel):
    """Total time a party held the ball across all of its segments."""

    party: str | None
    dwell_days: float
    segment_count: int


class OwnershipChainOut(BaseModel):
    """Reconstructed ownership history for one change record."""

    kind: str
    entity_id: str
    project_id: str
    as_of: str
    current_holder: str | None
    ownership_ambiguous: bool
    has_current_holder: bool
    has_unrecorded_origin: bool
    chain_inconsistent: bool
    unchanged_across_transition: bool
    total_handoffs: int
    ambiguity_reasons: list[str]
    segments: list[OwnershipSegmentOut]
    dwell_by_party: list[PartyDwellOut]


# --- Dispute-exposure radar (#7) -------------------------------------------
# Money is carried as a string (the Decimal rendered losslessly) per the
# platform money-as-string convention, so these rows are built explicitly in
# the router rather than validated straight off the engine dataclasses.


class RiskFactorOut(BaseModel):
    """One weighted risk factor's contribution to a change's dispute exposure."""

    name: str
    weight: int
    fraction: float
    weighted: float
    is_driver: bool


class DisputeRiskItemOut(BaseModel):
    """The graded dispute exposure of one open change."""

    change_id: str
    change_ref: str
    kind: str
    title: str
    exposure_score: int
    band: str
    dominant_driver: str
    recommended_cure: str
    intrinsic_exposure: float
    money_multiplier: float
    money_basis: str
    currency: str
    factors: list[RiskFactorOut]


class CurrencyExposureOut(BaseModel):
    """Exposure-weighted money at risk for a single currency (never blended)."""

    currency: str
    item_count: int
    money_basis_total: str
    exposure_weighted_amount: str


class DisputeExposureSummaryOut(BaseModel):
    """Portfolio roll-up over a project's ranked dispute-risk items."""

    item_count: int
    band_counts: dict[str, int]
    by_currency: list[CurrencyExposureOut]
    top_driver_counts: dict[str, int]


class DisputeRiskBoardOut(BaseModel):
    """Ranked dispute-exposure board for a project's open changes."""

    project_id: str
    generated_at: str
    items: list[DisputeRiskItemOut]
    summary: DisputeExposureSummaryOut


# --- Decision-time impact preview (#13) ------------------------------------
# Every money / day figure is serialized as a string so the signed Decimal
# round-trips losslessly and currencies are never blended on the wire.


class DecisionImpactRowOut(BaseModel):
    """Before / after position for one (kind, currency) at the decision point."""

    kind: str
    currency: str
    current_committed_cost: str
    candidate_cost_delta: str
    resulting_cost: str
    current_committed_days: str
    candidate_days_delta: str
    resulting_days: str


class CurrencyTotalOut(BaseModel):
    """All-kinds rollup of the decision preview for a single currency."""

    currency: str
    current_committed_cost: str
    candidate_cost_delta: str
    resulting_cost: str
    current_committed_days: str
    candidate_days_delta: str
    resulting_days: str


class DecisionImpactOut(BaseModel):
    """Decision-time preview: what approving the candidate adds to the baseline."""

    project_id: str
    candidate_change_id: str
    candidate_kind: str
    candidate_currency: str
    rows: list[DecisionImpactRowOut]
    totals_by_currency: list[CurrencyTotalOut]


# --- Proactive change watch (#18) ------------------------------------------


class WatchResultOut(BaseModel):
    """The watch classification of one change."""

    change_id: str
    kind: str
    classification: str
    reasons: list[str]
    idle_days: float
    overdue_days: float


class ChangeWatchOut(BaseModel):
    """Project-wide watch roll-up: which open changes are drifting and why."""

    project_id: str
    generated_at: str
    item_count: int
    counts: dict[str, int]
    items: list[WatchResultOut]
