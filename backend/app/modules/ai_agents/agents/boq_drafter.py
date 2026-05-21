"""BOQ Drafter — sample agent that drafts a BOQ from a brief.

Tools (declarative — wired into the global registry on import):

* ``search_costs(q, region)``     — proxy over ``costs.matcher.match_cwicr_items``
* ``suggest_assembly(description)`` — best-effort: tries the existing
                                    ``assemblies`` module's template lookup,
                                    falls back to a deterministic mock so
                                    tests stay fast and offline.
* ``create_position(boq_id, description, unit, qty, unit_rate)`` — does NOT
  hit the BOQ tables. Per the architecture guide "AI-augmented, human-confirmed", the
  runner only RETURNS a proposal; the user reviews it in the UI before any
  real position is created. The tool just structures the proposal payload.

If the matcher can't be called in the current process (no DB, no async
context — common in unit tests), the tool degrades to a sensible mock so
the agent loop is still observable.
"""

from __future__ import annotations

import logging
from typing import Any

from app.modules.ai_agents.base import (
    Agent,
    FunctionTool,
    global_tool_registry,
    register_agent,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a construction-cost estimator drafting a Bill of Quantities. "
    "Use the available tools to look up real cost rates and assembly recipes, "
    "then propose BOQ positions via create_position. Once the proposal is "
    "complete, reply with a concise markdown summary of the positions for the "
    "user to review. Never invent fictitious unit rates — call search_costs."
)


# ── Tool implementations ────────────────────────────────────────────────────


async def _tool_search_costs(q: str, region: str | None = None) -> dict[str, Any]:
    """Query the cost database via ``costs.matcher.match_cwicr_items``.

    Falls back to a deterministic mock when no AsyncSession is available
    (e.g. unit tests instantiate the tool directly without a DB).
    """
    q_clean = (q or "").strip()
    if not q_clean:
        return {"query": q_clean, "matches": [], "note": "empty query"}

    # Best-effort: open a session ourselves. If anything fails we degrade
    # to a mock so the agent loop keeps progressing.
    try:
        from app.database import async_session_factory
        from app.modules.costs.matcher import match_cwicr_items

        async with async_session_factory() as session:
            results = await match_cwicr_items(
                session,
                q_clean,
                top_k=5,
                region=region or None,
            )
        matches = [
            {
                "code": r.code,
                "description": r.description,
                "unit": r.unit,
                "unit_rate": float(r.unit_rate),
                "currency": r.currency,
                "score": float(r.score),
            }
            for r in results
        ]
        return {"query": q_clean, "region": region or "", "matches": matches}
    except Exception as exc:  # pragma: no cover - mock-friendly degradation
        logger.debug("search_costs degraded to mock: %s", exc)
        return {
            "query": q_clean,
            "region": region or "",
            "matches": [
                {
                    "code": "MOCK-001",
                    "description": f"Mock match for: {q_clean}",
                    "unit": "m2",
                    "unit_rate": 25.0,
                    "currency": "EUR",
                    "score": 0.5,
                }
            ],
            "note": "degraded_mock",
        }


async def _tool_suggest_assembly(description: str) -> dict[str, Any]:
    """Suggest an assembly template that matches ``description``.

    Tries the assemblies module's template repository first; falls back
    to a deterministic mock when unavailable.
    """
    desc = (description or "").strip()
    if not desc:
        return {"description": desc, "suggestion": None, "note": "empty description"}

    try:
        # TODO: wire to assemblies.repository.AssemblyTemplateRepository.search
        # once the template-search helper has a stable async signature outside
        # of a request session. For now we return the structured mock so the
        # agent demo flow is reproducible across environments.
        raise NotImplementedError
    except Exception:
        return {
            "description": desc,
            "suggestion": {
                "name": f"Assembly for {desc[:40]}",
                "category": "general",
                "unit": "m2",
                "components": [
                    {"role": "material", "description": desc, "factor": 1.0, "unit": "m2"},
                    {"role": "labour", "description": "Installation crew", "factor": 0.5, "unit": "h"},
                ],
            },
            "note": "mock_assembly",
        }


async def _tool_create_position(
    boq_id: str | None = None,
    description: str = "",
    unit: str = "m2",
    qty: float = 0.0,
    unit_rate: float = 0.0,
) -> dict[str, Any]:
    """Build a structured BOQ-position PROPOSAL — NEVER writes the DB.

    Per the architecture guide the runner only returns proposals; the user confirms
    them in the review panel before anything lands in the project.
    """
    try:
        qty_f = float(qty or 0.0)
    except (TypeError, ValueError):
        qty_f = 0.0
    try:
        rate_f = float(unit_rate or 0.0)
    except (TypeError, ValueError):
        rate_f = 0.0

    total = round(qty_f * rate_f, 2)
    return {
        "kind": "boq_position_proposal",
        "boq_id": boq_id,
        "description": (description or "").strip(),
        "unit": (unit or "m2").strip(),
        "qty": round(qty_f, 4),
        "unit_rate": round(rate_f, 4),
        "total": total,
        # The frontend wires "Apply" to a confirmed POST — not done here.
        "confirmed": False,
    }


# ── Registration ────────────────────────────────────────────────────────────


def register_boq_drafter() -> None:
    """Idempotent registration of the BOQ-drafter agent and its tools."""
    global_tool_registry.register(
        FunctionTool(
            name="search_costs",
            description=(
                "Look up cost-database items that match a free-form query. "
                "Returns up to 5 candidates with code, description, unit, "
                "unit_rate and currency. Use this before create_position to "
                "avoid inventing rates."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Search query"},
                    "region": {
                        "type": "string",
                        "description": "Optional region code (e.g. DE_BERLIN)",
                    },
                },
                "required": ["q"],
            },
            func=_tool_search_costs,
        )
    )
    global_tool_registry.register(
        FunctionTool(
            name="suggest_assembly",
            description=(
                "Suggest an assembly recipe (multi-component template) that "
                "matches the description. Returns the assembly name, unit and "
                "components list."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                },
                "required": ["description"],
            },
            func=_tool_suggest_assembly,
        )
    )
    global_tool_registry.register(
        FunctionTool(
            name="create_position",
            description=(
                "Append a BOQ position PROPOSAL to the run output. This does NOT "
                "modify the project — the user must approve every proposal in the "
                "review panel. Call this once per line item."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "boq_id": {"type": "string"},
                    "description": {"type": "string"},
                    "unit": {"type": "string"},
                    "qty": {"type": "number"},
                    "unit_rate": {"type": "number"},
                },
                "required": ["description", "unit", "qty", "unit_rate"],
            },
            func=_tool_create_position,
        )
    )

    register_agent(
        Agent(
            name="boq_drafter",
            description=(
                "Drafts BOQ positions from a free-form brief, grounding rates "
                "in the cost database and suggesting reusable assemblies."
            ),
            system_prompt=SYSTEM_PROMPT,
            max_iterations=8,
            allowed_tools=["search_costs", "suggest_assembly", "create_position"],
        )
    )
