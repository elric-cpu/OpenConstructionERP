"""AI Agents ORM models.

Tables:
    oe_ai_agents_run  — one row per agent invocation (status, totals, output).
    oe_ai_agents_step — chronological steps within a run
                        (thought / tool_call / observation / answer / error).

Both tables are append-only from a user's perspective (the runner writes
incrementally as the loop progresses; the API only ever lets you create
a new run or fetch existing ones — no in-place edits).
"""

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class AgentRun(Base):
    """A single agent invocation — the ReAct loop bookkeeping row."""

    __tablename__ = "oe_ai_agents_run"

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    # running | completed | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    # Free-form reason when status=failed (e.g. "iter_limit", "llm_error").
    failure_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Final answer (markdown text) or structured proposal serialised as JSON-in-string.
    final_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    def __repr__(self) -> str:
        return f"<AgentRun {self.id} agent={self.agent_name} status={self.status}>"


class AgentStep(Base):
    """One entry in a run's ReAct timeline.

    ``role`` values: ``thought`` (LLM reasoning text), ``tool_call``
    (LLM asked to invoke a tool — ``content`` is ``{name, args}``),
    ``observation`` (tool returned — ``content`` is the result or error),
    ``answer`` (LLM emitted final text — ``content`` is ``{text}``),
    ``error`` (out-of-band failure: unknown tool, parse error, ...).
    """

    __tablename__ = "oe_ai_agents_step"

    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_ai_agents_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[dict | list | str | None] = mapped_column(  # type: ignore[assignment]
        JSON,
        nullable=False,
        default=dict,
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<AgentStep run={self.run_id} idx={self.step_idx} role={self.role}>"
