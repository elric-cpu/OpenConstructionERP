"""AI Agents Pydantic schemas — request/response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Agent metadata ──────────────────────────────────────────────────────────


class AgentDescriptor(BaseModel):
    """A registered agent surfaced to clients."""

    name: str
    description: str
    system_prompt: str = ""
    max_iterations: int = 8
    allowed_tools: list[str] = Field(default_factory=list)


class ToolDescriptor(BaseModel):
    """A tool the agent runner can dispatch to."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


# ── Run create / read ───────────────────────────────────────────────────────


class CreateAgentRunRequest(BaseModel):
    """Request body for ``POST /ai-agents/runs/``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    agent_name: str = Field(..., min_length=1, max_length=100)
    project_id: UUID | None = None
    user_input: str = Field(..., min_length=1, max_length=10_000)


class AgentStepResponse(BaseModel):
    """One step in a run's vertical timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_idx: int
    role: str
    content: Any = None
    token_count: int = 0
    created_at: datetime


class AgentRunResponse(BaseModel):
    """Full run snapshot — status, totals, every step so far."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_name: str
    project_id: UUID | None = None
    user_id: UUID
    status: str
    failure_reason: str | None = None
    user_input: str
    final_output: str | None = None
    iterations: int = 0
    total_tokens: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[AgentStepResponse] = Field(default_factory=list)


class AgentRunListItem(BaseModel):
    """Lightweight row for the run list endpoint (no steps)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_name: str
    project_id: UUID | None = None
    user_id: UUID
    status: str
    failure_reason: str | None = None
    iterations: int = 0
    total_tokens: int = 0
    created_at: datetime
    updated_at: datetime


# ── Health ──────────────────────────────────────────────────────────────────


class AgentHealthResponse(BaseModel):
    """Pre-flight check so the UI can warn before the user wastes a click.

    Returned by ``GET /ai-agents/health/``. ``llm_configured`` is the only
    field the UI strictly needs; ``provider`` / ``model`` are surfaced so
    the page can show "Will run on Anthropic claude-sonnet-4-5" reassurance.
    """

    llm_configured: bool
    provider: str | None = None
    model: str | None = None
    settings_url: str = "/settings/ai"
