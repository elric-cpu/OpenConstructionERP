"""AI Agents framework — Slice 1.

Provides a generic ReAct-style agent loop on top of the single-call
``ai`` module LLM client. Adds a Tool protocol + ToolRegistry so each
agent can declare exactly which side-effect-free helpers it is allowed
to call, plus per-run persistence (``AgentRun`` + ``AgentStep``) so the
UI can render a vertical timeline of every thought / tool call /
observation / answer.

The runner NEVER auto-applies an agent's output to the BOQ /
project — it returns the proposal so the user can review it in the
review panel (the architecture guide "AI-augmented, human-confirmed" principle).
"""


async def on_startup() -> None:
    """Module startup hook — register permissions + built-in agents."""
    from app.modules.ai_agents.agents.boq_drafter import register_boq_drafter
    from app.modules.ai_agents.permissions import register_ai_agents_permissions

    register_ai_agents_permissions()
    register_boq_drafter()
