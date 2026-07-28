"""Redis settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class RedisSettings:
    """Redis settings."""

    # ── Redis ───────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
