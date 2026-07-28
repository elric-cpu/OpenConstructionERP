"""Rate limits settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class RateLimitsSettings:
    """Rate limits settings."""

    # ── Rate Limits ───────────────────────────────────────────────────────
    api_rate_limit: int = Field(
        default=100,
        description="API rate limit per minute per IP",
        ge=1,
    )
    login_rate_limit: int = Field(
        default=10,
        description="Login rate limit per minute per IP",
        ge=1,
    )
    ai_rate_limit: int = Field(
        default=50,
        description="AI rate limit per minute per IP",
        ge=1,
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
