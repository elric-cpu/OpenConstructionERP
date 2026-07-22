"""Point Cloud ingest settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class PointCloudSettings:
    """Point Cloud ingest settings."""

    # ── Point Cloud ingest ───────────────────────────────────────────────
    # Reality-capture scans are 5-200 GB. They are uploaded
    # presigned-direct-to-MinIO so the 2 GB FastAPI core never proxies the
    # bytes; the backend only mints the key, hands back presigned part URLs
    # and finalises the multipart upload. These tunables bound the rare
    # fallback proxied path and apply back-pressure on the init endpoint.
    #
    # Multipart part size in bytes. S3 requires every part except the last to
    # be at least 5 MiB and allows at most 10000 parts, so the default 64 MiB
    # supports a single multipart upload up to ~640 GB - comfortably above the
    # 200 GB ceiling we target. Env: ``OE_POINTCLOUD_PART_SIZE_BYTES``.
    pointcloud_part_size_bytes: int = Field(default=64 * 1024 * 1024, ge=5 * 1024 * 1024)
    # Lifetime of every presigned URL (init parts) in seconds. Long
    # enough that a slow link can finish a 200 GB upload (default 12 hours)
    # but still short-lived so a leaked URL expires.
    # Env: ``OE_POINTCLOUD_PRESIGN_EXPIRE_SECONDS``.
    pointcloud_presign_expire_seconds: int = Field(default=12 * 3600, ge=60)
    # Hard ceiling (bytes) on ANY proxied upload that falls back through the
    # FastAPI core instead of going direct to object storage. The direct
    # presigned path has no such limit; this cap exists only so a misrouted
    # or worker-less deployment cannot push a multi-GB body through the 2 GB
    # core and OOM the box. Default 512 MiB. Env:
    # ``OE_POINTCLOUD_MAX_PROXIED_BYTES``.
    pointcloud_max_proxied_bytes: int = Field(default=512 * 1024 * 1024, ge=0)
    # Maximum number of ingest init requests allowed in flight at once
    # (back-pressure). Each init touches object storage to open a multipart
    # upload; on a small VPS a flood of inits would exhaust connections, so
    # the init endpoint acquires a process-global gate and returns 429 with an
    # explanatory reason when the gate is full rather than degrade the whole
    # process. Default 8. Env: ``OE_POINTCLOUD_MAX_CONCURRENT_INGEST``.
    pointcloud_max_concurrent_ingest: int = Field(default=8, ge=1, le=256)

    model_config = SettingsConfigDict(env_prefix="OE_")
