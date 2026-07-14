from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BENSON_", env_file=".env", extra="ignore")

    app_name: str = "Benson Operations"
    environment: Literal["development", "test", "production"] = "development"
    currency: Literal["USD"] = "USD"
    country_code: Literal["US"] = "US"
    state_code: Literal["OR"] = "OR"
    county: Literal["Harney"] = "Harney"
    timezone: str = "America/Los_Angeles"
    unit_system: Literal["imperial"] = "imperial"

    website_api_key: str = Field(default="development-only", min_length=8)
    fcc_base_url: AnyHttpUrl = "http://127.0.0.1:8082"
    fcc_auth_token: str = Field(default="freecc", min_length=1)
    fcc_model: str = "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
    ai_max_steps: int = Field(default=12, ge=1, le=30)
    ai_timeout_seconds: int = Field(default=90, ge=5, le=300)

    quickbooks_client_id: str = ""
    quickbooks_client_secret: str = ""
    quickbooks_environment: Literal["sandbox", "production"] = "sandbox"
    upload_base_url: AnyHttpUrl = "https://erp.bensonhomesolutions.com"
    upload_max_bytes: int = Field(default=15_000_000, ge=1_000_000, le=25_000_000)
    upload_storage_path: Path = Path("./private-uploads")
    database_path: Path = Path("./benson-operations.sqlite3")


@lru_cache
def get_settings() -> Settings:
    return Settings()
