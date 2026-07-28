from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from .auth import Principal, require_operations_staff
from .change_order_domain import (
    ChangeOrderCreate,
    ChangeOrderEvidenceSummary,
    ChangeOrderRevisionCreate,
    ChangeOrderSummary,
    ChangeOrderTransition,
    ChangeOrderUpdate,
)
from .change_order_store import ChangeOrderStaleWrite
from .config import Settings, get_settings
from .dependencies import store
from .domain import Role
from .object_storage import (
    delete_upload,
    detect_upload_type,
    read_upload,
    sanitize_field_photo,
    store_change_order_evidence,
)

router = APIRouter(prefix="/api/benson/v1/change-orders", tags=["change-orders"])


def _conflict(error: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


@router.get("", response_model=list[ChangeOrderSummary])
def list_change_orders(
    job_id: UUID | None = None,
    status_filter: Annotated[str, Query(alias="status")] = "",
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[ChangeOrderSummary]:
    return store(settings).list_change_orders(
        job_id=str(job_id) if job_id else None, status=status_filter
    )


@router.post("", response_model=ChangeOrderSummary, status_code=status.HTTP_201_CREATED)
def create_change_order(
    order: ChangeOrderCreate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> ChangeOrderSummary:
    try:
        return store(settings).create_change_order(order, actor=principal.email)
    except ValueError as error:
        raise _conflict(error) from error


@router.get("/{change_order_id}", response_model=ChangeOrderSummary)
def get_change_order(
    change_order_id: UUID,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> ChangeOrderSummary:
    order = store(settings).get_change_order(str(change_order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")
    return order


@router.patch("/{change_order_id}", response_model=ChangeOrderSummary)
def update_change_order(
    change_order_id: UUID,
    change: ChangeOrderUpdate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> ChangeOrderSummary:
    if not change.model_dump(exclude_unset=True, exclude={"expected_version"}):
        raise HTTPException(status_code=400, detail="A change order update is required")
    try:
        order = store(settings).update_change_order(
            str(change_order_id), change, actor=principal.email
        )
    except (ValueError, ChangeOrderStaleWrite) as error:
        raise _conflict(error) from error
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")
    return order


@router.post("/{change_order_id}/transition", response_model=ChangeOrderSummary)
def transition_change_order(
    change_order_id: UUID,
    transition: ChangeOrderTransition,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> ChangeOrderSummary:
    if transition.status in {"approved", "rejected", "void"} and principal.role not in {
        Role.OWNER,
        Role.ADMIN,
    }:
        raise HTTPException(status_code=403, detail="Owner approval required")
    if transition.status in {"approved", "rejected", "void"} and not (
        transition.note.strip()
    ):
        raise HTTPException(
            status_code=422, detail="A factual decision note is required"
        )
    try:
        order = store(settings).transition_change_order(
            str(change_order_id),
            target=transition.status,
            expected_version=transition.expected_version,
            note=transition.note,
            actor=principal.email,
        )
    except (ValueError, ChangeOrderStaleWrite) as error:
        raise _conflict(error) from error
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")
    return order


@router.post(
    "/{change_order_id}/revisions",
    response_model=ChangeOrderSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_change_order_revision(
    change_order_id: UUID,
    revision: ChangeOrderRevisionCreate,
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> ChangeOrderSummary:
    try:
        order = store(settings).create_change_order_revision(
            str(change_order_id),
            expected_version=revision.expected_version,
            reason=revision.reason,
            actor=principal.email,
        )
    except (ValueError, ChangeOrderStaleWrite) as error:
        raise _conflict(error) from error
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")
    return order


@router.post(
    "/{change_order_id}/evidence",
    response_model=ChangeOrderEvidenceSummary,
    status_code=status.HTTP_201_CREATED,
)
async def upload_change_order_evidence(
    change_order_id: UUID,
    evidence: Annotated[UploadFile, File()],
    principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> ChangeOrderEvidenceSummary:
    raw = await evidence.read(settings.upload_max_bytes + 1)
    if len(raw) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Evidence exceeds upload limit")
    detected = detect_upload_type(raw)
    if detected not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
        raise HTTPException(
            status_code=422, detail="Evidence must be JPEG, PNG, WebP, or PDF"
        )
    content = raw
    content_type = detected
    filename = evidence.filename or "evidence"
    if detected.startswith("image/"):
        content, content_type, suffix = sanitize_field_photo(raw)
        filename = f"{filename.rsplit('.', 1)[0]}{suffix}"
    storage_key, digest = store_change_order_evidence(
        settings,
        change_order_id=str(change_order_id),
        original_name=filename,
        content=content,
        content_type=content_type,
    )
    try:
        summary = store(settings).add_change_order_evidence(
            str(change_order_id),
            original_name=filename,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            actor=principal.email,
        )
    except ValueError as error:
        delete_upload(settings, storage_key)
        raise _conflict(error) from error
    if not summary:
        delete_upload(settings, storage_key)
        raise HTTPException(status_code=404, detail="Change order not found")
    return summary


@router.get(
    "/{change_order_id}/evidence", response_model=list[ChangeOrderEvidenceSummary]
)
def list_change_order_evidence(
    change_order_id: UUID,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[ChangeOrderEvidenceSummary]:
    evidence = store(settings).list_change_order_evidence(str(change_order_id))
    if evidence is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    return evidence


@router.get("/{change_order_id}/evidence/{evidence_id}/download")
def download_change_order_evidence(
    change_order_id: UUID,
    evidence_id: UUID,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> Response:
    evidence = store(settings).get_change_order_evidence(
        str(change_order_id), str(evidence_id)
    )
    if not evidence:
        raise HTTPException(status_code=404, detail="Change order evidence not found")
    filename = evidence["original_name"].replace('"', "")
    return Response(
        content=read_upload(settings, evidence["storage_key"]),
        media_type=evidence["content_type"],
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{change_order_id}/audit")
def change_order_audit(
    change_order_id: UUID,
    _principal: Principal = Depends(require_operations_staff),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    events = store(settings).list_change_order_audit(str(change_order_id))
    if events is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    return events
