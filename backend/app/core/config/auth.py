"""Authentication settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class AuthSettings:
    """Authentication settings."""

    # ── Auth ─────────────────────────────────────────────────────────────
    jwt_secret: str = Field(
        default="openestimate-local-dev-key",
        description="Secret key for JWT signing",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for JWT signing",
    )
    jwt_expire_minutes: int = Field(
        default=60,
        description="JWT access token expiration in minutes",
    )
    jwt_refresh_expire_days: int = Field(
        default=30,
        description="JWT refresh token expiration in days",
    )
    default_registration_role: str = Field(
        default="viewer",
        description="Default role for new user registrations",
    )
    registration_mode: str = Field(
        default="open",
        description="Registration mode (open, invite_only, closed)",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
