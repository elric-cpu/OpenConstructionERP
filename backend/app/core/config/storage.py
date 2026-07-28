"""Storage settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class StorageSettings:
    """Storage settings."""

    # ── Storage ───────────────────────────────────────────────────────────
    storage_backend: str = Field(
        default="local",
        description="Storage backend to use (local, s3, etc.)",
    )
    s3_endpoint: str = Field(
        default="",
        description="S3-compatible endpoint URL (for non-AWS S3)",
    )
    s3_access_key: str = Field(
        default="",
        description="S3 access key",
    )
    s3_secret_key: str = Field(
        default="",
        description="S3 secret key",
    )
    s3_bucket: str = Field(
        default="",
        description="S3 bucket name",
    )
    s3_region: str = Field(
        default="us-east-1",
        description="S3 region",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
