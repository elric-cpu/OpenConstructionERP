"""AI Agents service — business logic for starting and inspecting runs.

The service is what wires the in-process :class:`AgentRunner` to:
    1. The DB-backed :class:`AgentRun` / :class:`AgentStep` persistence.
    2. The production LLM bridge (or whichever bridge the caller injects).
    3. The user's AI settings (provider + api_key + model id).

Tests instantiate the service with a custom LLM bridge to avoid hitting
external providers; production passes ``None`` and the service resolves
the bridge via :mod:`app.modules.ai.ai_client`.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_agents.base import (
    Agent,
    AgentResult,
    AgentRunner,
    LLMBridge,
    StepRecord,
    ToolRegistry,
    get_agent,
    global_tool_registry,
    list_agents,
)
from app.modules.ai_agents.models import AgentRun, AgentStep
from app.modules.ai_agents.repository import AgentRunRepository, AgentStepRepository

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    """Wall-clock UTC ISO string (kept short to fit String(40))."""
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


async def _resolve_production_llm(session: AsyncSession, user_id: uuid.UUID) -> LLMBridge | None:
    """Pull the user's AI settings and build a :class:`CallAILLM` bridge.

    Returns ``None`` when no API key is configured — the caller decides
    whether that's a hard error (it is, for ``run_agent``).
    """
    try:
        from app.modules.ai.ai_client import resolve_provider_key_model
        from app.modules.ai.repository import AISettingsRepository
        from app.modules.ai_agents.llm import CallAILLM
    except Exception as exc:  # pragma: no cover - import safety
        logger.warning("AI module unavailable for agent runner: %s", exc)
        return None

    settings = await AISettingsRepository(session).get_by_user_id(user_id)
    try:
        provider, api_key, model = resolve_provider_key_model(settings)
    except ValueError:
        return None
    return CallAILLM(provider=provider, api_key=api_key, model=model)


def _humanize_agent(name: str) -> str:
    """Turn an agent slug (``boq_generator``) into a label (``Boq Generator``)."""
    return name.replace("_", " ").replace("-", " ").strip().title() or "AI agent"


def _coerce_confidence(value: Any) -> float | None:
    """Normalise a confidence to the 0.0-1.0 range the UI expects.

    Agents emit confidence on either a 0-1 or a 0-100 scale; anything above 1
    is treated as a percentage and divided down. Non-numeric input yields None.
    """
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return None
    if conf > 1.0:
        conf = conf / 100.0
    return max(0.0, min(conf, 1.0))


def _run_to_insight(run: AgentRun) -> dict[str, Any]:
    """Distill one completed :class:`AgentRun` into a project-insight card.

    Structured JSON output (``{"title", "summary", "confidence", "severity"}``)
    is used directly; plain-text output falls back to the agent's humanised name
    as the title and its first line as the summary. This is real run output, not
    a placeholder.
    """
    raw = (run.final_output or "").strip()
    title: str | None = None
    summary: str | None = None
    confidence: float | None = None
    severity: str | None = None

    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            title = payload.get("title") or payload.get("headline")
            summary = payload.get("summary") or payload.get("message") or payload.get("recommendation")
            confidence = _coerce_confidence(payload.get("confidence"))
            sev = payload.get("severity")
            severity = str(sev) if sev is not None else None

    if not title:
        title = _humanize_agent(run.agent_name)
    if not summary:
        first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
        summary = (first_line[:200] + "...") if len(first_line) > 200 else (first_line or None)
    if severity is None:
        severity = "info"

    return {
        "id": str(run.id),
        "title": str(title)[:200],
        "summary": summary,
        "confidence": confidence,
        "severity": severity,
    }


class AgentService:
    """High-level façade over the runner + persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.run_repo = AgentRunRepository(session)
        self.step_repo = AgentStepRepository(session)

    # ── Catalogue ────────────────────────────────────────────────────────

    def list_registered_agents(self) -> list[Agent]:
        return list_agents()

    def list_registered_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in global_tool_registry.all()
        ]

    # ── Run lifecycle ────────────────────────────────────────────────────

    async def start_run(
        self,
        *,
        user_id: uuid.UUID,
        agent_name: str,
        user_input: str,
        project_id: uuid.UUID | None = None,
        llm: LLMBridge | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> AgentRun:
        """Create the run row, execute the loop synchronously, and persist steps.

        "Background task" wiring (``BackgroundTasks.add_task``) lives in
        the router — here we just run the loop. The router can choose to
        ``await`` us inline (tests do) or schedule us for later.
        """
        agent = get_agent(agent_name)
        if agent is None:
            msg = f"Unknown agent: {agent_name}"
            raise ValueError(msg)

        run = AgentRun(
            agent_name=agent_name,
            project_id=project_id,
            user_id=user_id,
            status="running",
            user_input=user_input,
            iterations=0,
            total_tokens=0,
            started_at=_iso_now(),
        )
        run = await self.run_repo.create(run)
        run_id = run.id

        # Resolve LLM bridge (caller may inject one for tests).
        bridge = llm
        if bridge is None:
            bridge = await _resolve_production_llm(self.session, user_id)
        if bridge is None:
            await self.run_repo.update_fields(
                run_id,
                status="failed",
                failure_reason="no_llm",
                finished_at=_iso_now(),
            )
            refreshed = await self.run_repo.get_by_id(run_id)
            assert refreshed is not None  # noqa: S101
            return refreshed

        step_counter = {"i": 0}

        async def _persist(step: StepRecord) -> None:
            step_counter["i"] += 1
            await self.step_repo.create(
                AgentStep(
                    run_id=run_id,
                    step_idx=step_counter["i"],
                    role=step.role,
                    content=step.content,
                    token_count=step.token_count,
                )
            )

        runner = AgentRunner(bridge, on_step=_persist)
        context = {"project_id": str(project_id)} if project_id else None

        try:
            result: AgentResult = await runner.run(
                agent,
                user_input,
                context=context,
                tool_registry=tool_registry,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Agent run %s crashed", run_id)
            await self.run_repo.update_fields(
                run_id,
                status="failed",
                failure_reason="exception",
                final_output=str(exc)[:500],
                finished_at=_iso_now(),
            )
            refreshed = await self.run_repo.get_by_id(run_id)
            assert refreshed is not None  # noqa: S101
            return refreshed

        await self.run_repo.update_fields(
            run_id,
            status=result.status,
            failure_reason=result.failure_reason,
            final_output=result.final_output,
            iterations=result.iterations,
            total_tokens=result.total_tokens,
            finished_at=_iso_now(),
        )
        refreshed = await self.run_repo.get_by_id(run_id)
        assert refreshed is not None  # noqa: S101
        return refreshed

    # ── Read ─────────────────────────────────────────────────────────────

    async def get_run(self, run_id: uuid.UUID) -> AgentRun | None:
        return await self.run_repo.get_by_id(run_id)

    async def get_run_steps(self, run_id: uuid.UUID) -> list[AgentStep]:
        return await self.step_repo.list_for_run(run_id)

    async def list_runs(
        self,
        *,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        return await self.run_repo.list_runs(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
        )

    async def project_insights(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int = 2,
    ) -> list[dict[str, Any]]:
        """Return the user's most recent useful AI results for a project.

        Only completed runs that produced output become insights, so we
        over-fetch recent runs and stop once ``limit`` real insights are
        collected. Scoped to the caller's own runs, mirroring the privacy
        model of the run-detail endpoint.
        """
        runs = await self.run_repo.list_runs(
            user_id=user_id,
            project_id=project_id,
            limit=max(limit * 5, 10),
        )
        insights: list[dict[str, Any]] = []
        for run in runs:
            if run.status != "completed" or not (run.final_output or "").strip():
                continue
            insights.append(_run_to_insight(run))
            if len(insights) >= limit:
                break
        return insights
