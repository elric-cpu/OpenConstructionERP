import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response as BinaryResponse
from pydantic import ValidationError

from .auth import Principal, require_operations_staff, require_owner, require_staff
from .config import Settings, get_settings
from .dependencies import store
from .domain import LeadCreate, LeadReceipt, LeadUpdate
from .integration_audit import integration_audit_json
from .object_storage import (
    delete_upload,
    detect_upload_type,
    read_upload,
    store_upload,
)
from .signing import verify_website_signature
from .storage import IdempotencyConflict, InvalidLeadTransition

router = APIRouter()
logger = logging.getLogger(__name__)
_allowed_upload_types = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


def create_lead_receipt(
    lead: LeadCreate,
    idempotency_key: str,
    settings: Settings,
) -> LeadReceipt:
    operations = store(settings)
    sms_enabled = operations.notification_settings(
        sms_enabled_default=settings.sms_enabled_default
    )["sms_enabled"]
    return operations.create_or_get_lead(
        idempotency_key=idempotency_key,
        lead=lead,
        upload_base_url=str(settings.upload_base_url),
        upload_session_hours=settings.upload_session_hours,
        notification_email_to=settings.notification_email_to,
        emergency_sms_to=settings.sms_to if sms_enabled else "",
        client_sms_to=(lead.phone if sms_enabled and lead.consent_to_contact else ""),
        notification_max_attempts=settings.notification_max_attempts,
    )


@router.get("/api/v1/dashboard")
def dashboard(
    principal: Principal = Depends(require_staff),
    settings: Settings = Depends(get_settings),
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


@router.post("/api/v1/intake/leads", response_model=LeadReceipt)
@router.post("/api/benson/v1/intake/leads", response_model=LeadReceipt)
async def benson_website_lead(
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_benson_timestamp: Annotated[
        str | None, Header(alias="X-Benson-Timestamp")
    ] = None,
    x_benson_signature: Annotated[
        str | None, Header(alias="X-Benson-Signature")
    ] = None,
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
        raise HTTPException(
            status_code=400, detail="A valid Idempotency-Key is required"
        )
    try:
        lead = LeadCreate.model_validate_json(body)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=json.loads(error.json())) from error
    geo = lead.metadata.get("geo_coordinates", {})
    latitude_value = geo.get("latitude") if isinstance(geo, dict) else None
    longitude_value = geo.get("longitude") if isinstance(geo, dict) else None
    try:
        latitude = float(latitude_value) if latitude_value is not None else None
        longitude = float(longitude_value) if longitude_value is not None else None
        if latitude is not None and longitude is not None:
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail="Geo-coordinates are outside valid bounds"
        ) from error
    try:
        receipt = await run_in_threadpool(
            create_lead_receipt, lead, idempotency_key, settings
        )
    except IdempotencyConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    response.status_code = (
        status.HTTP_200_OK if receipt.duplicate else status.HTTP_201_CREATED
    )
    logger.info(
        integration_audit_json(
            event="public_intake.accepted",
            calling_ip=request.client.host if request.client else "unknown",
            request_id=request.headers.get("X-Request-ID", ""),
            latitude=latitude,
            longitude=longitude,
            target_delta={
                "lead_id": str(receipt.lead_id),
                "status": receipt.status,
                "duplicate": receipt.duplicate,
            },
        )
    )
    return receipt


@router.get("/api/benson/v1/leads")
def list_leads(
    limit: int = 100,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    query: str | None = None,
    source: str | None = None,
    spam: Literal["active", "spam", "all"] = "active",
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
            source=source,
            spam=spam,
        )
    }


@router.get("/api/benson/v1/leads/{lead_id}")
def lead_detail(
    lead_id: str,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    lead = store(settings).get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/api/benson/v1/leads/{lead_id}")
def update_lead(
    lead_id: str,
    change: LeadUpdate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not change.model_dump(exclude_none=True):
        raise HTTPException(
            status_code=400, detail="At least one lead change is required"
        )
    if change.assigned_to is not None:
        assignable_emails = {member["email"] for member in settings.assignable_staff()}
        if str(change.assigned_to).lower() not in assignable_emails:
            raise HTTPException(
                status_code=422,
                detail="Lead assignee must be an authorized staff member",
            )
    try:
        lead = store(settings).update_lead(lead_id, change, actor=principal.email)
    except InvalidLeadTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.delete("/api/benson/v1/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(
    lead_id: str,
    principal: Principal = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> Response:
    if not store(settings).delete_lead(lead_id, actor=principal.email):
        raise HTTPException(status_code=404, detail="Lead not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/benson/v1/attachments/{attachment_id}")
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


@router.get("/uploads/{session_id}", response_class=HTMLResponse)
def upload_handoff(session_id: str, settings: Settings = Depends(get_settings)) -> str:
    if not store(settings).get_upload_session(session_id):
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )
    return """<!doctype html><html><head><meta name=viewport content='width=device-width'><title>Add project photos | Benson</title><style>:root{color-scheme:light}body{margin:0;background:#f5f1e8;color:#2d2d2d;font:16px 'IBM Plex Sans',system-ui}main{max-width:560px;margin:8vh auto;background:#faf8f3;padding:clamp(24px,6vw,48px);border-top:6px solid #722f37;box-shadow:0 20px 60px #4a1f2420}h1{font-family:Newsreader,Georgia,serif;font-size:42px;line-height:1.05;color:#4a1f24}button{background:#722f37;color:white;border:0;padding:14px 20px;font-weight:700;border-radius:4px}input{display:block;margin:24px 0;width:100%}small{color:#8b454d;letter-spacing:.12em;font-weight:700}</style></head><body><main><small>BENSON HOME SOLUTIONS</small><h1>Your request is saved.</h1><p>Add project photos or a PDF to help us prepare for the first review.</p><form method=post enctype=multipart/form-data><input type=file name=files accept='image/jpeg,image/png,image/webp,application/pdf' multiple required><button>Attach files</button></form></main></body></html>"""


@router.post("/uploads/{session_id}", response_class=HTMLResponse)
async def receive_uploads(
    session_id: str,
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> str:
    session = await run_in_threadpool(store(settings).get_upload_session, session_id)
    if not session:
        raise HTTPException(
            status_code=404, detail="Upload session not found or expired"
        )
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
