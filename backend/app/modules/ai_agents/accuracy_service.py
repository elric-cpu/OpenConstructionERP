# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Accuracy scoreboard service for AI agent runs.

Reads the trust confidence persisted on each :class:`AgentRun` together with a
recorded actual outcome and scores every agent's calibration with the pure
:mod:`app.modules.ai_agents.accuracy` engine. The outcome is stored back inside
the run's ``trust`` JSON (a fresh dict is assigned so SQLAlchemy detects the
change), so no schema migration is needed to turn a stated confidence into a
scored prediction.

Privacy: every read is scoped to the caller's own runs, mirroring the run
detail and insights endpoints, so the scoreboard never exposes another user's
agent activity.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_agents.accuracy import (
    AccuracyScore,
    Prediction,
    clamp01,
    score_by_agent,
)
from app.modules.ai_agents.models import AgentRun

#: Keys written into the run's trust JSON when an outcome is recorded.
OUTCOME_KEY = "actual_outcome"
OUTCOME_AT_KEY = "outcome_recorded_at"
OUTCOME_BY_KEY = "outcome_recorded_by"
OUTCOME_NOTE_KEY = "outcome_note"


def _confidence_of(trust: object) -> float | None:
    """Extract a usable [0,1] confidence from a run's trust JSON, or None."""
    if not isinstance(trust, dict):
        return None
    raw = trust.get("confidence")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return clamp01(float(raw))
    except (TypeError, ValueError):
        return None


def _outcome_of(trust: object) -> bool | None:
    """Extract the recorded actual outcome from a run's trust JSON, or None."""
    if not isinstance(trust, dict):
        return None
    value = trust.get(OUTCOME_KEY)
    return value if isinstance(value, bool) else None


async def record_run_outcome(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    correct: bool,
    recorded_by: uuid.UUID,
    note: str | None = None,
) -> AgentRun | None:
    """Record whether an agent run turned out correct, scoped to its owner.

    Returns the updated run, or ``None`` when the run does not exist or does not
    belong to *recorded_by* (so a caller can never write an outcome onto another
    user's run). The outcome is merged into a fresh copy of the trust JSON.
    """
    run = (
        await session.execute(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == recorded_by))
    ).scalar_one_or_none()
    if run is None:
        return None

    trust = dict(run.trust) if isinstance(run.trust, dict) else {}
    trust[OUTCOME_KEY] = bool(correct)
    trust[OUTCOME_AT_KEY] = datetime.now(UTC).isoformat()
    trust[OUTCOME_BY_KEY] = str(recorded_by)
    if note:
        trust[OUTCOME_NOTE_KEY] = note
    run.trust = trust  # reassign so the JSON column change is flushed
    await session.flush()
    return run


async def build_scoreboard(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    agent_name: str | None = None,
) -> list[AccuracyScore]:
    """Score each agent's calibration over the caller's own scored runs.

    A run contributes a prediction only when it carries both a usable trust
    confidence and a recorded actual outcome. Results are ordered by agent name
    for a stable response.
    """
    stmt = select(AgentRun.agent_name, AgentRun.trust).where(AgentRun.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(AgentRun.project_id == project_id)
    if agent_name:
        stmt = stmt.where(AgentRun.agent_name == agent_name)

    predictions: list[Prediction] = []
    for row in (await session.execute(stmt)).all():
        confidence = _confidence_of(row.trust)
        outcome = _outcome_of(row.trust)
        if confidence is None or outcome is None:
            continue
        predictions.append(Prediction(agent_name=row.agent_name, confidence=confidence, outcome=outcome))

    scored = score_by_agent(predictions)
    return [scored[name] for name in sorted(scored)]
