"""External services settings domain."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict


class ExternalServicesSettings:
    """External services settings."""

    # ── External Services ─────────────────────────────────────────────────
    openweathermap_api_key: str = Field(
        default="",
        description="OpenWeatherMap API key for weather data",
    )

    model_config = SettingsConfigDict(env_prefix="OE_")
