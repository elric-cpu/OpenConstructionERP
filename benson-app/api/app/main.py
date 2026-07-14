from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse

from .ai_gateway import AiGatewayUnavailable, run_agent_prompt
from .config import Settings, get_settings
from .domain import AgentActionRequest, AgentActionResult, BENSON_MODULES, LeadIntake, LeadReceipt, Role
from .policy import ActionRisk, evaluate_agent_action
from .storage import OperationsStore

app = FastAPI(
    title="Benson Operations API",
    version="0.1.0",
    description="Focused residential contractor operations for Benson Home Solutions.",
)

_audit: list[dict] = []
_upload_sessions: dict[str, dict] = {}
_allowed_upload_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def store(settings: Settings) -> OperationsStore:
    return OperationsStore(settings.database_path)


def require_website_key(
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if x_api_key != settings.website_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid website key")


@app.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "profile": {"currency": "USD", "state": "OR", "county": "Harney"},
    }


@app.get("/api/v1/config/modules")
async def modules(role: Role = Role.OWNER) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for module in BENSON_MODULES:
        if role in module.roles:
            grouped[module.group].append({"id": module.id, "label": module.label})
    return {"role": role, "groups": grouped}


@app.get("/api/v1/dashboard")
async def dashboard(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "generated_at": datetime.now(UTC),
        "metrics": {"new_leads": store(settings).lead_count(), "active_jobs": 0, "open_tasks": 0, "unbilled_work": 0},
        "attention": [],
        "schedule": [],
        "jobs": [],
    }


@app.post(
    "/api/v1/webhook-leads/incoming/benson-website/",
    response_model=LeadReceipt,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_website_key)],
)
async def website_lead(lead: LeadIntake, settings: Settings = Depends(get_settings)) -> LeadReceipt:
    receipt = LeadReceipt(upload_url="")
    receipt.upload_url = f"{str(settings.upload_base_url).rstrip('/')}/uploads/{receipt.upload_session_id}"
    store(settings).save_lead(receipt, lead)
    _upload_sessions[str(receipt.upload_session_id)] = {"lead_id": str(receipt.lead_id), "files": []}
    _audit.append({"event": "lead.accepted", "lead_id": str(receipt.lead_id), "at": receipt.accepted_at.isoformat()})
    return receipt


@app.get("/uploads/{session_id}", response_class=HTMLResponse)
async def upload_handoff(session_id: str) -> str:
    if session_id not in _upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return """<!doctype html><html><head><meta name=viewport content='width=device-width'><title>Add project photos | Benson</title><style>body{margin:0;background:#f3f0e9;color:#351011;font:16px system-ui}main{max-width:560px;margin:8vh auto;background:white;padding:clamp(24px,6vw,48px);border-top:6px solid #6c1d20}h1{font-family:Georgia,serif;font-size:38px}button{background:#6c1d20;color:white;border:0;padding:14px 20px;font-weight:700}input{display:block;margin:24px 0;width:100%}small{color:#706b64}</style></head><body><main><small>BENSON HOME SOLUTIONS</small><h1>Your request is saved.</h1><p>Add photos or a PDF now to help us understand the project. You can safely close this page if you do not have them handy.</p><form method=post enctype=multipart/form-data><input type=file name=files accept='image/jpeg,image/png,image/webp,application/pdf' multiple required><button>Attach files</button></form></main></body></html>"""


@app.post("/uploads/{session_id}", response_class=HTMLResponse)
async def receive_uploads(
    session_id: str,
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> str:
    session = _upload_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if len(files) > 10:
        raise HTTPException(status_code=413, detail="Maximum 10 files")
    accepted = []
    storage = settings.upload_storage_path.resolve()
    storage.mkdir(mode=0o700, parents=True, exist_ok=True)
    for upload in files:
        if upload.content_type not in _allowed_upload_types:
            raise HTTPException(status_code=415, detail="Unsupported file type")
        content = await upload.read(settings.upload_max_bytes + 1)
        if len(content) > settings.upload_max_bytes:
            raise HTTPException(status_code=413, detail="File too large")
        suffix = Path(upload.filename or "").suffix.lower()[:10]
        stored_name = f"{uuid4().hex}{suffix}"
        destination = storage / stored_name
        destination.write_bytes(content)
        destination.chmod(0o600)
        accepted.append({"name": upload.filename, "stored_name": stored_name, "type": upload.content_type, "size": len(content)})
    session["files"].extend(accepted)
    _audit.append({"event": "lead.files_attached", "lead_id": session["lead_id"], "count": len(accepted), "at": datetime.now(UTC).isoformat()})
    return "<main style='max-width:560px;margin:10vh auto;font:18px system-ui'><h1>Files attached.</h1><p>Thank you. Benson Home Solutions will review your request and follow up.</p></main>"


@app.post("/api/v1/agent/actions", response_model=AgentActionResult)
async def agent_action(request: AgentActionRequest, settings: Settings = Depends(get_settings)) -> AgentActionResult:
    requested_risks = [
        ActionRisk(prefix)
        for tool in request.tools
        if (prefix := tool.split(":", 1)[0]) in ActionRisk._value2member_map_
    ]
    decisions = [evaluate_agent_action(request.role, risk) for risk in requested_risks]
    if any(not decision.allowed for decision in decisions):
        raise HTTPException(status_code=403, detail="Requested tool exceeds role permissions")
    confirmation_required = any(decision.confirmation_required for decision in decisions)
    system = (
        "You are the Benson Operations assistant. Work only with the supplied records. "
        "Never invent customer, price, scope, schedule, legal, or payment facts. Return a concise action summary."
    )
    try:
        response = await run_agent_prompt(settings, request.prompt, system)
        summary = str(response.get("output_text") or "Agent response completed")
    except AiGatewayUnavailable:
        return AgentActionResult(status="failed", summary="AI gateway unavailable; no records were changed", model=settings.fcc_model)
    result = AgentActionResult(
        status="confirmation_required" if confirmation_required else "completed",
        summary=summary,
        proposed_actions=[{"tool": tool, "confirmation_required": confirmation_required} for tool in request.tools],
        model=settings.fcc_model,
    )
    _audit.append({"event": "agent.run", "run_id": str(result.run_id), "role": request.role, "at": result.audited_at.isoformat()})
    return result
