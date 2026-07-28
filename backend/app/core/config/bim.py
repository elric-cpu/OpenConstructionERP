"""BIM settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class BIMSettings:
    """BIM settings."""

    # ── BIM ──────────────────────────────────────────────────────────────
    keep_original_cad: bool = Field(
        default=False,
        description="Whether to keep original CAD files after processing",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
