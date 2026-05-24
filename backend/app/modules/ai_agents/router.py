"""AI Agents API routes.

Endpoints (mounted at ``/api/v1/ai-agents/`` by the module loader):

* ``GET    /agents/``            — registered agents (with allowed_tools)
* ``GET    /tools/``             — registered tools (debugging surface)
* ``POST   /runs/``              — start a new run (returns id immediately;
                                    loop runs in a background task)
* ``GET    /runs/``              — list runs (newest first; optional
                                    project_id filter)
* ``GET    /runs/{id}``          — full run snapshot incl. steps timeline
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.dependencies import CurrentUserId, RequirePermission, SessionDep
from app.modules.ai_agents.schemas import (
    AgentDescriptor,
    AgentHealthResponse,
    AgentRunListItem,
    AgentRunResponse,
    AgentStepResponse,
    CreateAgentRunRequest,
    ToolDescriptor,
)
from app.modules.ai_agents.service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Idempotency cache ────────────────────────────────────────────────────
# In-memory map of ``(user_id, idempotency_key) -> (run_id, created_ts)``.
# Purpose: protect agent runs from frontend retry storms / duplicate
# submits — each agent run costs real LLM dollars, so re-running on a
# transient network blip would burn cash silently. Entries expire after
# IDEMPOTENCY_TTL_SECONDS.
#
# Single-process scope is acceptable for now (single-tenant VPS deploy);
# multi-instance prod will need Redis backing (TODO).
IDEMPOTENCY_TTL_SECONDS = 600  # 10 minutes
_IDEMPOTENCY_CACHE: dict[tuple[str, str], tuple[uuid.UUID, float]] = {}


def _idempotency_lookup(user_id: str, key: str) -> uuid.UUID | None:
    """Return the cached run_id for this user+key, or None if absent/expired."""
    now = time.monotonic()
    # Lazy eviction of stale entries (cheap; cache is tiny).
    stale = [k for k, (_, ts) in _IDEMPOTENCY_CACHE.items() if now - ts > IDEMPOTENCY_TTL_SECONDS]
    for k in stale:
        _IDEMPOTENCY_CACHE.pop(k, None)
    entry = _IDEMPOTENCY_CACHE.get((user_id, key))
    if entry is None:
        return None
    return entry[0]


def _idempotency_record(user_id: str, key: str, run_id: uuid.UUID) -> None:
    _IDEMPOTENCY_CACHE[(user_id, key)] = (run_id, time.monotonic())


def _get_service(session: SessionDep) -> AgentService:
    return AgentService(session)


# ── Agent / tool catalogues ──────────────────────────────────────────────


@router.get(
    "/agents/",
    response_model=list[AgentDescriptor],
    dependencies=[Depends(RequirePermission("ai_agents.read"))],
)
async def list_agents_endpoint(
    service: AgentService = Depends(_get_service),
) -> list[AgentDescriptor]:
    """List every registered agent — name, prompt, allowed tools."""
    return [
        AgentDescriptor(
            name=a.name,
            description=a.description,
            system_prompt=a.system_prompt,
            max_iterations=a.max_iterations,
            allowed_tools=a.allowed_tools,
        )
        for a in service.list_registered_agents()
    ]


@router.get(
    "/tools/",
    response_model=list[ToolDescriptor],
    dependencies=[Depends(RequirePermission("ai_agents.read"))],
)
async def list_tools_endpoint(
    service: AgentService = Depends(_get_service),
) -> list[ToolDescriptor]:
    """List every tool the runner can dispatch to."""
    return [ToolDescriptor(**t) for t in service.list_registered_tools()]


@router.get(
    "/health/",
    response_model=AgentHealthResponse,
    dependencies=[Depends(RequirePermission("ai_agents.read"))],
)
async def agents_health(
    user_id: CurrentUserId,
    session: SessionDep,
) -> AgentHealthResponse:
    """Cheap pre-flight: does the caller have a usable LLM provider?

    The Agents page polls this on mount so it can warn before the user
    spends a turn writing a prompt only to get a cryptic ``no_llm`` row
    on the runs timeline. We resolve provider/key/model exactly the way
    ``_resolve_production_llm`` does, but never instantiate the bridge.
    """
    uid = uuid.UUID(user_id)
    try:
        from app.modules.ai.ai_client import resolve_provider_key_model
        from app.modules.ai.repository import AISettingsRepository
    except Exception:  # pragma: no cover - import safety
        return AgentHealthResponse(llm_configured=False)

    settings = await AISettingsRepository(session).get_by_user_id(uid)
    try:
        provider, _api_key, model = resolve_provider_key_model(settings)
    except ValueError:
        return AgentHealthResponse(llm_configured=False)
    return AgentHealthResponse(
        llm_configured=True,
        provider=provider,
        model=model,
    )


# ── Run lifecycle ────────────────────────────────────────────────────────


async def _run_in_background(
    *,
    user_id: uuid.UUID,
    agent_name: str,
    user_input: str,
    project_id: uuid.UUID | None,
    run_id: uuid.UUID,
) -> None:
    """Background-task entry point — opens its own session.

    The FastAPI-supplied session is gone by the time the background
    task runs (the response has already been returned to the client),
    so we open a fresh session bound to the same async engine.
    """
    async with async_session_factory() as bg_session:
        try:
            service = AgentService(bg_session)
            # The run row already exists (created in the foreground); we
            # just resume the loop by calling start_run-equivalent logic.
            # Simplest path: reuse start_run but it would create a second
            # row. Instead we go a level deeper and drive the runner here.
            from app.modules.ai_agents.base import AgentRunner, StepRecord
            from app.modules.ai_agents.models import AgentStep
            from app.modules.ai_agents.service import _iso_now, _resolve_production_llm

            agent = service.list_registered_agents()
            target = next((a for a in agent if a.name == agent_name), None)
            if target is None:
                await service.run_repo.update_fields(
                    run_id,
                    status="failed",
                    failure_reason="unknown_agent",
                    finished_at=_iso_now(),
                )
                await bg_session.commit()
                return

            bridge = await _resolve_production_llm(bg_session, user_id)
            if bridge is None:
                await service.run_repo.update_fields(
                    run_id,
                    status="failed",
                    failure_reason="no_llm",
                    finished_at=_iso_now(),
                )
                await bg_session.commit()
                return

            step_counter = {"i": 0}

            async def _persist(step: StepRecord) -> None:
                step_counter["i"] += 1
                await service.step_repo.create(
                    AgentStep(
                        run_id=run_id,
                        step_idx=step_counter["i"],
                        role=step.role,
                        content=step.content,
                        token_count=step.token_count,
                    )
                )
                await bg_session.commit()

            runner = AgentRunner(bridge, on_step=_persist)
            context = {"project_id": str(project_id)} if project_id else None
            result = await runner.run(target, user_input, context=context)

            await service.run_repo.update_fields(
                run_id,
                status=result.status,
                failure_reason=result.failure_reason,
                final_output=result.final_output,
                iterations=result.iterations,
                total_tokens=result.total_tokens,
                finished_at=_iso_now(),
            )
            await bg_session.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Background agent run %s crashed", run_id)
            try:
                from app.modules.ai_agents.repository import AgentRunRepository
                from app.modules.ai_agents.service import _iso_now

                await AgentRunRepository(bg_session).update_fields(
                    run_id,
                    status="failed",
                    failure_reason="exception",
                    final_output=str(exc)[:500],
                    finished_at=_iso_now(),
                )
                await bg_session.commit()
            except Exception:
                pass


@router.post(
    "/runs/",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission("ai_agents.run"))],
)
async def create_run(
    request: CreateAgentRunRequest,
    background_tasks: BackgroundTasks,
    user_id: CurrentUserId,
    session: SessionDep,
    service: AgentService = Depends(_get_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AgentRunResponse:
    """Start a new run.

    Returns immediately after persisting a ``running`` row; the agent
    loop continues in a FastAPI background task. Poll
    ``GET /runs/{id}`` for progress (the steps timeline updates as
    the loop emits each step).

    Idempotency: clients may pass ``Idempotency-Key`` header to make
    retries safe. Submitting the same key within 10 minutes returns the
    original run instead of spawning a duplicate (agent runs cost real
    LLM dollars — never let a retry storm double-spend).
    """
    uid = uuid.UUID(user_id)

    # Idempotency replay: return existing run for the same key within TTL.
    if idempotency_key:
        existing_run_id = _idempotency_lookup(user_id, idempotency_key)
        if existing_run_id is not None:
            existing = await service.get_run(existing_run_id)
            if existing is not None and str(existing.user_id) == user_id:
                steps = await service.get_run_steps(existing_run_id)
                return _serialise_run(existing, steps=steps)

    # Validate that the agent exists before creating the row.
    from app.modules.ai_agents.base import get_agent

    if get_agent(request.agent_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent: {request.agent_name}",
        )

    from app.modules.ai_agents.models import AgentRun
    from app.modules.ai_agents.service import _iso_now

    run = AgentRun(
        agent_name=request.agent_name,
        project_id=request.project_id,
        user_id=uid,
        status="running",
        user_input=request.user_input,
        started_at=_iso_now(),
    )
    run = await service.run_repo.create(run)
    await session.commit()

    if idempotency_key:
        _idempotency_record(user_id, idempotency_key, run.id)

    background_tasks.add_task(
        _run_in_background,
        user_id=uid,
        agent_name=request.agent_name,
        user_input=request.user_input,
        project_id=request.project_id,
        run_id=run.id,
    )

    return _serialise_run(run, steps=[])


@router.get(
    "/runs/",
    response_model=list[AgentRunListItem],
    dependencies=[Depends(RequirePermission("ai_agents.read"))],
)
async def list_runs(
    user_id: CurrentUserId,
    project_id: uuid.UUID | None = None,
    limit: int = 50,
    service: AgentService = Depends(_get_service),
) -> list[AgentRunListItem]:
    """List the caller's recent runs. ``project_id`` optionally narrows."""
    uid = uuid.UUID(user_id)
    runs = await service.list_runs(user_id=uid, project_id=project_id, limit=limit)
    return [AgentRunListItem.model_validate(r) for r in runs]


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunResponse,
    dependencies=[Depends(RequirePermission("ai_agents.read"))],
)
async def get_run(
    run_id: uuid.UUID,
    user_id: CurrentUserId,
    service: AgentService = Depends(_get_service),
) -> AgentRunResponse:
    """Return the full run incl. ordered steps timeline."""
    uid = uuid.UUID(user_id)
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if str(run.user_id) != str(uid):
        raise HTTPException(status_code=403, detail="You can only view your own runs")
    steps = await service.get_run_steps(run_id)
    return _serialise_run(run, steps=steps)


# ── Serialisation helper ─────────────────────────────────────────────────


def _serialise_run(run: Any, *, steps: list[Any]) -> AgentRunResponse:
    """Convert ORM models to the response schema."""
    return AgentRunResponse(
        id=run.id,
        agent_name=run.agent_name,
        project_id=run.project_id,
        user_id=run.user_id,
        status=run.status,
        failure_reason=run.failure_reason,
        user_input=run.user_input,
        final_output=run.final_output,
        iterations=run.iterations,
        total_tokens=run.total_tokens,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
        steps=[AgentStepResponse.model_validate(s) for s in steps],
    )


# Silence "imported but unused" — kept for type imports used at runtime.
_ = AsyncSession
