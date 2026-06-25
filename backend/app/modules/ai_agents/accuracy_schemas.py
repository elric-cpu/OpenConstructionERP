# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the AI accuracy scoreboard endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RecordOutcomeIn(BaseModel):
    """Request body recording whether an agent run turned out correct."""

    correct: bool
    note: str | None = None


class OutcomeRecordedOut(BaseModel):
    """Acknowledgement that an outcome was recorded on a run."""

    run_id: str
    agent_name: str
    actual_outcome: bool


class CalibrationBinOut(BaseModel):
    """One reliability bucket over the confidence range."""

    model_config = ConfigDict(from_attributes=True)

    lower: float
    upper: float
    count: int
    mean_confidence: float
    observed_rate: float


class AccuracyScoreOut(BaseModel):
    """Aggregate accuracy and calibration summary for one agent."""

    model_config = ConfigDict(from_attributes=True)

    agent_name: str
    count: int
    brier_score: float
    mean_confidence: float
    observed_rate: float
    calibration_error: float
    bins: list[CalibrationBinOut]


class AccuracyScoreboardOut(BaseModel):
    """The accuracy scoreboard: one score per agent the caller has run."""

    scores: list[AccuracyScoreOut]


class SandboxSeedOut(BaseModel):
    """Result of seeding the demo sandbox with sample scored agent runs."""

    # How many runs this call created (0 when they already existed - the seed
    # is idempotent), the total sample-run count, and the distinct agent names.
    created: int
    total: int
    agents: list[str]
