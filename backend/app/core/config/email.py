"""Email settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class EmailSettings:
    """Email settings."""

    # ── Email ───────────────────────────────────────────────────────────
    email_backend: str = Field(
        default="smtp",
        description="Email backend to use (smtp, console, etc.)",
    )
    smtp_host: str = Field(
        default="localhost",
        description="SMTP server host",
    )
    smtp_port: int = Field(
        default=587,
        description="SMTP server port",
        ge=1,
        le=65535,
    )
    smtp_user: str = Field(
        default="",
        description="SMTP username",
    )
    smtp_password: str = Field(
        default="",
        description="SMTP password",
    )
    smtp_tls: bool = Field(
        default=True,
        description="Enable TLS for SMTP",
    )
    smtp_ssl: bool = Field(
        default=False,
        description="Enable SSL for SMTP",
    )
    smtp_from_email: str = Field(
        default="noreply@openconstructionerp.com",
        description="Default sender email address",
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Frontend URL for email links",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
