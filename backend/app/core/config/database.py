"""Database settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class DatabaseSettings:
    """Database settings."""

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = Field(
        default="",
        description="PostgreSQL database URL for async SQLAlchemy (e.g., postgresql+asyncpg://user:pass@host/db)",
    )
    database_sync_url: str = Field(
        default="",
        description="PostgreSQL database URL for sync SQLAlchemy (e.g., postgresql+psycopg2://user:pass@host/db)",
    )
    database_pool_size: int = Field(
        default=10,
        description="Database connection pool size",
    )
    database_max_overflow: int = Field(
        default=20,
        description="Database connection pool max overflow",
    )
    database_echo: bool = Field(
        default=False,
        description="Whether to echo SQL statements",
    )
    database_pool_recycle: int = Field(
        default=3600,
        description="Database connection pool recycle time in seconds",
    )
    max_batch_size: int = Field(
        default=100,
        description="Maximum batch size for database operations",
    )
    slow_query_ms: int = Field(
        default=1000,
        description="Slow query threshold in milliseconds",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
