import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from .ai_gateway import AiGatewayUnavailable, run_agent_prompt
from .auth import Principal, require_owner, require_staff
from .config import Settings, get_settings
from .dependencies import store
from .domain import AgentRunRequest, ProposalDecision
from .policy import ActionRisk
from .skill_registry import SkillDefinition, load_registry

router = APIRouter()


def registry(settings: Settings) -> Any:
    return load_registry(str(settings.resolved_ddc_registry_path()))


@router.get("/api/benson/v1/ai/skills")
async def ai_skills(
    principal: Principal = Depends(require_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    catalog = registry(settings)
    return {
        "source_commit": catalog.source_commit,
        "skills": catalog.visible_to(principal.role),
    }


def skill_system_prompt(skill: SkillDefinition) -> str:
    return (
        "You are the Benson Operations assistant using the reviewed construction skill "
        f"'{skill.label}'. Work only with supplied records and cite which supplied facts support each conclusion. "
        "Never invent customer, price, scope, schedule, legal, safety, or payment facts. "
        "Return a concise draft. You cannot mutate records or send communications."
    )


def lead_ai_context(lead: dict[str, Any]) -> dict[str, Any]:
    intake = lead["payload"]
    return {
        "lead": {
            "id": lead["id"],
            "status": lead["status"],
            "priority": lead["priority"],
            "assigned": bool(lead.get("assigned_to")),
            "service_type": lead["service_type"],
            "city": lead["city"],
            "urgency": intake.get("urgency"),
            "customer_type": intake.get("customer_type"),
            "item_count": intake.get("item_count"),
            "dimensions": intake.get("dimensions"),
            "access_notes": intake.get("access_notes"),
            "timeline": intake.get("timeline"),
            "project_description": intake.get("message"),
            "staff_notes": [note["body"] for note in lead["notes"]],
            "attachment_count": len(lead["attachments"]),
        }
    }


@router.post("/api/benson/v1/ai/runs")
async def run_ai_skill(
    request: AgentRunRequest,
    principal: Principal = Depends(require_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    skill = registry(settings).get(request.skill_id)
    if not skill or not skill.enabled or principal.role not in skill.allowed_roles:
        raise HTTPException(
            status_code=404, detail="Skill is not available for this role"
        )
    lead = await run_in_threadpool(store(settings).get_lead, str(request.lead_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead was not found")
    record_context = lead_ai_context(lead)
    context_json = json.dumps(record_context, sort_keys=True)
    if len(context_json.encode()) > 50_000:
        raise HTTPException(status_code=413, detail="AI record context is too large")
    model_prompt = f"{request.prompt}\n\nSupplied record context:\n{context_json}"
    try:
        result = await run_agent_prompt(
            settings, model_prompt, skill_system_prompt(skill)
        )
        summary = str(result.get("output_text") or "Draft completed")
        run_status = (
            "confirmation_required"
            if skill.risk != ActionRisk.INTERNAL
            else "completed"
        )
    except AiGatewayUnavailable:
        summary = "AI gateway unavailable; no records were changed"
        run_status = "failed"
    run_id, proposal_id = await run_in_threadpool(
        store(settings).create_ai_run,
        skill_id=skill.id,
        actor=principal.email,
        role=principal.role,
        status=run_status,
        prompt=request.prompt,
        summary=summary,
        model=settings.fcc_model,
        context=record_context,
        risk=skill.risk if run_status != "failed" else ActionRisk.INTERNAL,
    )
    return {
        "run_id": run_id,
        "status": run_status,
        "summary": summary,
        "proposal_id": proposal_id,
        "model": settings.fcc_model,
    }


async def decide_proposal(
    proposal_id: str,
    approved: bool,
    decision: ProposalDecision,
    principal: Principal,
    settings: Settings,
) -> dict[str, Any]:
    changed = await run_in_threadpool(
        store(settings).decide_proposal,
        proposal_id,
        approved=approved,
        actor=principal.email,
        comment=decision.comment,
    )
    if not changed:
        raise HTTPException(
            status_code=409, detail="Proposal is missing or already decided"
        )
    return {
        "proposal_id": proposal_id,
        "status": "approved" if approved else "rejected",
    }


@router.post("/api/benson/v1/ai/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    decision: ProposalDecision,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await decide_proposal(proposal_id, True, decision, principal, settings)


@router.post("/api/benson/v1/ai/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    decision: ProposalDecision,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await decide_proposal(proposal_id, False, decision, principal, settings)
