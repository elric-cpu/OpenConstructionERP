from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from .auth import Principal, require_field_records_user
from .config import Settings, get_settings
from .dependencies import store
from .domain import STAFF
from .field_record_domain import (
    FieldPhotoSummary,
    FieldReportCorrection,
    FieldReportCreate,
    FieldReportSummary,
    FieldReportUpdate,
    PhotoStage,
)
from .field_record_store import FieldReportStaleWrite
from .object_storage import (
    delete_upload,
    read_upload,
    sanitize_field_photo,
    store_field_photo,
)

router = APIRouter(prefix="/api/benson/v1/field-records", tags=["field-records"])


def _conflict(error: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


@router.get("", response_model=list[FieldReportSummary])
def list_field_reports(
    job_id: UUID | None = None,
    service_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> list[FieldReportSummary]:
    return store(settings).list_field_reports(
        actor=principal.email,
        role=principal.role,
        job_id=str(job_id) if job_id else None,
        service_date=service_date,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=FieldReportSummary, status_code=status.HTTP_201_CREATED)
def create_field_report(
    report: FieldReportCreate,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldReportSummary:
    try:
        created = store(settings).create_field_report(
            report, actor=principal.email, role=principal.role
        )
    except ValueError as error:
        raise _conflict(error) from error
    if not created:
        raise HTTPException(status_code=404, detail="Job not found")
    return created


@router.get("/{report_id}", response_model=FieldReportSummary)
def get_field_report(
    report_id: UUID,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldReportSummary:
    report = store(settings).get_field_report(
        str(report_id), actor=principal.email, role=principal.role
    )
    if not report:
        raise HTTPException(status_code=404, detail="Field report not found")
    return report


@router.put("/{report_id}", response_model=FieldReportSummary)
def update_field_report(
    report_id: UUID,
    change: FieldReportUpdate,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldReportSummary:
    try:
        report = store(settings).update_field_report(
            str(report_id),
            change,
            expected_version=change.expected_version,
            actor=principal.email,
            role=principal.role,
        )
    except (ValueError, FieldReportStaleWrite) as error:
        raise _conflict(error) from error
    if not report:
        raise HTTPException(status_code=404, detail="Field report not found")
    return report


@router.post("/{report_id}/submit", response_model=FieldReportSummary)
def submit_field_report(
    report_id: UUID,
    expected_version: Annotated[int, Query(ge=1)],
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldReportSummary:
    try:
        report = store(settings).submit_field_report(
            str(report_id),
            expected_version=expected_version,
            actor=principal.email,
            role=principal.role,
        )
    except (ValueError, FieldReportStaleWrite) as error:
        raise _conflict(error) from error
    if not report:
        raise HTTPException(status_code=404, detail="Field report not found")
    return report


@router.post("/{report_id}/correction", response_model=FieldReportSummary)
def request_correction(
    report_id: UUID,
    correction: FieldReportCorrection,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldReportSummary:
    if principal.role not in STAFF:
        raise HTTPException(
            status_code=403, detail="Field report review access required"
        )
    try:
        report = store(settings).request_field_report_correction(
            str(report_id),
            expected_version=correction.expected_version,
            reason=correction.reason,
            actor=principal.email,
        )
    except (ValueError, FieldReportStaleWrite) as error:
        raise _conflict(error) from error
    if not report:
        raise HTTPException(status_code=404, detail="Field report not found")
    return report


@router.post(
    "/{report_id}/revisions", response_model=FieldReportSummary, status_code=201
)
def create_revision(
    report_id: UUID,
    expected_version: Annotated[int, Query(ge=1)],
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldReportSummary:
    try:
        report = store(settings).create_field_report_revision(
            str(report_id),
            expected_version=expected_version,
            actor=principal.email,
            role=principal.role,
        )
    except (ValueError, FieldReportStaleWrite) as error:
        raise _conflict(error) from error
    if not report:
        raise HTTPException(status_code=404, detail="Field report not found")
    return report


@router.post("/{report_id}/photos", response_model=FieldPhotoSummary, status_code=201)
async def upload_photo(
    report_id: UUID,
    stage: Annotated[PhotoStage, Form()],
    photo: Annotated[UploadFile, File()],
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> FieldPhotoSummary:
    raw = await photo.read(settings.upload_max_bytes + 1)
    if len(raw) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Field photo exceeds upload limit")
    try:
        content, content_type, suffix = sanitize_field_photo(raw)
        storage_key, digest = store_field_photo(
            settings,
            report_id=str(report_id),
            content=content,
            suffix=suffix,
            content_type=content_type,
        )
        summary = store(settings).add_field_photo(
            str(report_id),
            stage=stage,
            original_name=photo.filename or f"photo{suffix}",
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=digest,
            actor=principal.email,
            role=principal.role,
        )
    except ValueError as error:
        if "storage_key" in locals():
            delete_upload(settings, storage_key)
        raise HTTPException(
            status_code=422
            if "decoded" in str(error) or "must be" in str(error)
            else 409,
            detail=str(error),
        ) from error
    if not summary:
        delete_upload(settings, storage_key)
        raise HTTPException(status_code=404, detail="Field report not found")
    return summary


@router.get("/{report_id}/photos", response_model=list[FieldPhotoSummary])
def list_photos(
    report_id: UUID,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> list[FieldPhotoSummary]:
    photos = store(settings).list_field_photos(
        str(report_id), actor=principal.email, role=principal.role
    )
    if photos is None:
        raise HTTPException(status_code=404, detail="Field report not found")
    return photos


@router.get("/{report_id}/photos/{photo_id}/download")
def download_photo(
    report_id: UUID,
    photo_id: UUID,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    photo = store(settings).get_field_photo(
        str(report_id), str(photo_id), actor=principal.email, role=principal.role
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Field photo not found")
    return Response(
        content=read_upload(settings, photo["storage_key"]),
        media_type=photo["content_type"],
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{photo["original_name"].replace(chr(34), "")}"',
        },
    )


@router.get("/{report_id}/audit")
def field_report_audit(
    report_id: UUID,
    principal: Principal = Depends(require_field_records_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    events = store(settings).list_field_report_audit(
        str(report_id), actor=principal.email, role=principal.role
    )
    if events is None:
        raise HTTPException(status_code=404, detail="Field report not found")
    return events
