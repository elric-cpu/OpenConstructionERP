import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .auth import require_notification_worker
from .config import Settings, get_settings
from .dependencies import store
from .integration_audit import integration_audit_json

router = APIRouter()
logger = logging.getLogger(__name__)


class PhotoAsset(BaseModel):
    """Picker-selected photo already copied into Benson-controlled storage."""

    storage_key: str = Field(min_length=1, max_length=1000)
    original_name: str = Field(min_length=1, max_length=500)
    content_type: str = Field(pattern=r"^image/[a-zA-Z0-9.+-]+$", max_length=120)
    size_bytes: int = Field(gt=0, le=25_000_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage: Literal["before", "during", "after"]
    picker_media_item_id: str | None = Field(default=None, max_length=500)
    captured_at: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhotoSyncRequest(BaseModel):
    work_order_id: str = Field(min_length=1, max_length=80)
    assets: list[PhotoAsset] = Field(min_length=1, max_length=100)


class SyncedAsset(BaseModel):
    asset_id: str
    created: bool
    sha256: str
    stage: Literal["before", "during", "after"]


class PhotoSyncReceipt(BaseModel):
    work_order_id: str
    assets: list[SyncedAsset]


@router.post(
    "/api/v1/assets/sync-google-photos",
    response_model=PhotoSyncReceipt,
    status_code=status.HTTP_200_OK,
)
async def sync_google_photos(
    payload: PhotoSyncRequest,
    request: Request,
    worker: str = Depends(require_notification_worker),
    settings: Settings = Depends(get_settings),
    x_request_id: Annotated[str, Header(alias="X-Request-ID")] = "",
) -> PhotoSyncReceipt:
    """Link Picker-selected, staged assets without exposing the ERP database."""
    operations = store(settings)
    results: list[SyncedAsset] = []
    for asset in payload.assets:
        metadata = {
            **asset.metadata,
            "picker_media_item_id": asset.picker_media_item_id,
            "captured_at": asset.captured_at,
            "geo_coordinates": {
                "latitude": asset.latitude,
                "longitude": asset.longitude,
                "source": "google_photos_picker_metadata",
            },
        }
        asset_id, created = await run_in_threadpool(
            operations.link_photo_asset_to_work_order,
            work_order_id=payload.work_order_id,
            storage_key=asset.storage_key,
            original_name=asset.original_name,
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            sha256=asset.sha256,
            actor=worker,
            asset_role=asset.stage,
            metadata=metadata,
        )
        results.append(
            SyncedAsset(
                asset_id=asset_id,
                created=created,
                sha256=asset.sha256,
                stage=asset.stage,
            )
        )
    logger.info(
        integration_audit_json(
            event="google_photos_picker.assets_linked",
            calling_ip=request.client.host if request.client else "unknown",
            request_id=x_request_id,
            target_delta={
                "work_order_id": payload.work_order_id,
                "asset_count": len(results),
                "created_count": sum(item.created for item in results),
            },
        )
    )
    return PhotoSyncReceipt(work_order_id=payload.work_order_id, assets=results)
