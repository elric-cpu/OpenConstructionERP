import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, Response as BinaryResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .ai_gateway import AiGatewayUnavailable, run_agent_prompt
from .auth import Principal, require_operations_staff, require_owner, require_staff
from .config import Settings, get_settings
from .domain import (
    AgentRunRequest,
    BENSON_MODULES,
    LeadCreate,
    LeadReceipt,
    LeadUpdate,
    ProposalDecision,
)
from .object_storage import delete_upload, detect_upload_type, read_upload, store_upload
from .policy import ActionRisk
from .signing import verify_website_signature
from .skill_registry import SkillDefinition, load_registry
from .storage import InvalidLeadTransition, OperationsStore, operations_store


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await run_in_threadpool(operations_store(settings.resolved_database_url()).initialize_schema)
    yield


app = FastAPI(
    title="Benson Operations API",
    version="0.2.0",
    description="Focused residential contractor operations for Benson Home Solutions.",
    lifespan=lifespan,
)
logger = logging.getLogger(__name__)

_allowed_upload_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def store(settings: Settings) -> OperationsStore:
    return operations_store(settings.resolved_database_url())


def create_lead_receipt(lead: LeadCreate, idempotency_key: str, settings: Settings) -> LeadReceipt:
    return store(settings).create_or_get_lead(
        idempotency_key=idempotency_key,
        lead=lead,
        upload_base_url=str(settings.upload_base_url),
        upload_session_hours=settings.upload_session_hours,
    )


@app.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": app.version,
        "profile": {"currency": "USD", "state": "OR", "county": "Harney"},
        "storage": "postgresql"
        if settings.resolved_database_url().startswith("postgresql")
        else "sqlite",
    }


@app.get("/api/benson/v1/auth/config")
async def auth_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "provider": "google_workspace",
        "client_id": settings.staff_google_audience,
        "hosted_domain": settings.staff_google_domain,
    }


@app.get("/api/v1/config/modules")
async def modules(principal: Principal = Depends(require_staff)) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for module in BENSON_MODULES:
        if principal.role in module.roles:
            grouped[module.group].append({"id": module.id, "label": module.label})
    return {"role": principal.role, "groups": grouped}


@app.get("/api/v1/dashboard")
def dashboard(
    principal: Principal = Depends(require_staff), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC),
        "actor": principal.email,
        "metrics": {
            "new_leads": store(settings).lead_count(),
            "active_jobs": 0,
            "open_tasks": 0,
            "unbilled_work": 0,
        },
        "attention": [],
        "schedule": [],
        "jobs": [],
    }


@app.post("/api/benson/v1/intake/leads", response_model=LeadReceipt)
async def benson_website_lead(
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_benson_timestamp: Annotated[str | None, Header(alias="X-Benson-Timestamp")] = None,
    x_benson_signature: Annotated[str | None, Header(alias="X-Benson-Signature")] = None,
    settings: Settings = Depends(get_settings),
) -> LeadReceipt:
    body = await request.body()
    verify_website_signature(
        secret=settings.website_signing_secret,
        timestamp=x_benson_timestamp,
        signature=x_benson_signature,
        body=body,
        max_age_seconds=settings.website_signature_max_age_seconds,
    )
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required")
    try:
        lead = LeadCreate.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=json.loads(error.json())) from error
    receipt = await run_in_threadpool(create_lead_receipt, lead, idempotency_key, settings)
    response.status_code = status.HTTP_200_OK if receipt.duplicate else status.HTTP_201_CREATED
    return receipt


@app.get("/api/benson/v1/leads")
def list_leads(
    limit: int = 100,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    query: str | None = None,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 250))
    return {
        "leads": store(settings).list_leads(
            safe_limit,
            status=status_filter,
            priority=priority,
            assigned_to=assigned_to,
            query=query,
        )
    }


@app.get("/api/benson/v1/leads/{lead_id}")
def lead_detail(
    lead_id: str,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    lead = store(settings).get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.patch("/api/benson/v1/leads/{lead_id}")
def update_lead(
    lead_id: str,
    change: LeadUpdate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if change.status is None and change.assigned_to is None and change.note is None:
        raise HTTPException(status_code=400, detail="At least one lead change is required")
    try:
        lead = store(settings).update_lead(lead_id, change, actor=principal.email)
    except InvalidLeadTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.get("/api/benson/v1/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> BinaryResponse:
    attachment = store(settings).get_attachment(attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    content = await run_in_threadpool(read_upload, settings, attachment["storage_key"])
    safe_name = Path(str(attachment["original_name"])).name.replace('"', "")
    return BinaryResponse(
        content,
        media_type=str(attachment["content_type"]),
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@app.get("/uploads/{session_id}", response_class=HTMLResponse)
def upload_handoff(session_id: str, settings: Settings = Depends(get_settings)) -> str:
    if not store(settings).get_upload_session(session_id):
        raise HTTPException(status_code=404, detail="Upload session not found or expired")
    return """<!doctype html><html><head><meta name=viewport content='width=device-width'><title>Add project photos | Benson</title><style>:root{color-scheme:light}body{margin:0;background:#f5f1e8;color:#2d2d2d;font:16px 'IBM Plex Sans',system-ui}main{max-width:560px;margin:8vh auto;background:#faf8f3;padding:clamp(24px,6vw,48px);border-top:6px solid #722f37;box-shadow:0 20px 60px #4a1f2420}h1{font-family:Newsreader,Georgia,serif;font-size:42px;line-height:1.05;color:#4a1f24}button{background:#722f37;color:white;border:0;padding:14px 20px;font-weight:700;border-radius:4px}input{display:block;margin:24px 0;width:100%}small{color:#8b454d;letter-spacing:.12em;font-weight:700}</style></head><body><main><small>BENSON HOME SOLUTIONS</small><h1>Your request is saved.</h1><p>Add project photos or a PDF to help us prepare for the first review.</p><form method=post enctype=multipart/form-data><input type=file name=files accept='image/jpeg,image/png,image/webp,application/pdf' multiple required><button>Attach files</button></form></main></body></html>"""


@app.post("/uploads/{session_id}", response_class=HTMLResponse)
async def receive_uploads(
    session_id: str,
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> str:
    session = await run_in_threadpool(store(settings).get_upload_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found or expired")
    if len(files) > 10:
        raise HTTPException(status_code=413, detail="Maximum 10 files")
    prepared: list[tuple[UploadFile, bytes, str]] = []
    for upload in files:
        content = await upload.read(settings.upload_max_bytes + 1)
        if len(content) > settings.upload_max_bytes:
            raise HTTPException(status_code=413, detail="File too large")
        detected = detect_upload_type(content)
        if detected not in _allowed_upload_types or detected != upload.content_type:
            raise HTTPException(
                status_code=415, detail="File content does not match an allowed type"
            )
        prepared.append((upload, content, detected))
    total_bytes = sum(len(content) for _, content, _ in prepared)
    reserved = await run_in_threadpool(
        store(settings).reserve_upload_capacity,
        session_id,
        file_count=len(prepared),
        size_bytes=total_bytes,
        max_files=settings.upload_session_max_files,
        max_bytes=settings.upload_session_max_bytes,
    )
    if not reserved:
        raise HTTPException(status_code=413, detail="Upload session capacity exceeded")
    stored_keys: list[str] = []
    attachment_items: list[dict[str, Any]] = []
    try:
        for upload, content, detected in prepared:
            original_name = Path(upload.filename or "upload").name
            storage_key, digest = await run_in_threadpool(
                store_upload,
                settings,
                lead_id=str(session["lead_id"]),
                original_name=original_name,
                content_type=detected,
                content=content,
            )
            stored_keys.append(storage_key)
            attachment_items.append(
                {
                    "original_name": original_name,
                    "storage_key": storage_key,
                    "content_type": detected,
                    "size_bytes": len(content),
                    "sha256": digest,
                }
            )
        await run_in_threadpool(
            store(settings).add_attachments,
            lead_id=str(session["lead_id"]),
            items=attachment_items,
        )
    except Exception:
        for storage_key in stored_keys:
            try:
                await run_in_threadpool(delete_upload, settings, storage_key)
            except Exception:
                logger.exception("Failed to remove an orphaned upload object")
        await run_in_threadpool(
            store(settings).release_upload_capacity,
            session_id,
            file_count=len(prepared),
            size_bytes=total_bytes,
        )
        raise
    return "<main style='max-width:560px;margin:10vh auto;font:18px system-ui'><h1>Files attached.</h1><p>Thank you. Benson Home Solutions will review your request and follow up.</p></main>"


def registry(settings: Settings) -> Any:
    return load_registry(str(settings.resolved_ddc_registry_path()))


@app.get("/api/benson/v1/ai/skills")
async def ai_skills(
    principal: Principal = Depends(require_staff), settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    catalog = registry(settings)
    return {"source_commit": catalog.source_commit, "skills": catalog.visible_to(principal.role)}


def skill_system_prompt(skill: SkillDefinition) -> str:
    return (
        "You are the Benson Operations assistant using the reviewed construction skill "
        f"'{skill.label}'. Work only with supplied records and cite which supplied facts support each conclusion. "
        "Never invent customer, price, scope, schedule, legal, safety, or payment facts. "
        "Return a concise draft. You cannot mutate records or send communications."
    )


@app.post("/api/benson/v1/ai/runs")
async def run_ai_skill(
    request: AgentRunRequest,
    principal: Principal = Depends(require_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    skill = registry(settings).get(request.skill_id)
    if not skill or not skill.enabled or principal.role not in skill.allowed_roles:
        raise HTTPException(status_code=404, detail="Skill is not available for this role")
    context_json = json.dumps(request.record_context, sort_keys=True)
    if len(context_json.encode()) > 50_000:
        raise HTTPException(status_code=413, detail="AI record context is too large")
    model_prompt = f"{request.prompt}\n\nSupplied record context:\n{context_json}"
    try:
        result = await run_agent_prompt(settings, model_prompt, skill_system_prompt(skill))
        summary = str(result.get("output_text") or "Draft completed")
        run_status = "confirmation_required" if skill.risk != ActionRisk.INTERNAL else "completed"
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
        context=request.record_context,
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
        raise HTTPException(status_code=409, detail="Proposal is missing or already decided")
    return {"proposal_id": proposal_id, "status": "approved" if approved else "rejected"}


@app.post("/api/benson/v1/ai/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    decision: ProposalDecision,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await decide_proposal(proposal_id, True, decision, principal, settings)


@app.post("/api/benson/v1/ai/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    decision: ProposalDecision,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await decide_proposal(proposal_id, False, decision, principal, settings)


_web_dist_path = get_settings().web_dist_path
if _web_dist_path is not None and _web_dist_path.is_dir():
    app.mount("/", StaticFiles(directory=_web_dist_path, html=True), name="web")
