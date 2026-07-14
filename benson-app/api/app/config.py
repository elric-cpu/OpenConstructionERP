from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, model_validator
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

    website_signing_secret: str = Field(default="development-signing-secret", min_length=16)
    website_signature_max_age_seconds: int = Field(default=300, ge=30, le=900)
    staff_google_audience: str = ""
    staff_google_domain: str = "bensonhomesolutions.com"
    owner_emails: str = "office@bensonhomesolutions.com"
    admin_emails: str = ""
    office_emails: str = ""
    estimator_pm_emails: str = ""
    accounting_emails: str = ""
    field_emails: str = ""
    fcc_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8082")
    fcc_auth_token: str = Field(default="freecc", min_length=1)
    fcc_model: str = "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
    ai_max_steps: int = Field(default=12, ge=1, le=30)
    ai_timeout_seconds: int = Field(default=90, ge=5, le=300)

    accounting_provider_client_id: str = ""
    accounting_provider_client_secret: str = ""
    accounting_provider_environment: Literal["sandbox", "production"] = "sandbox"
    upload_base_url: AnyHttpUrl = AnyHttpUrl("https://erp.bensonhomesolutions.com")
    upload_max_bytes: int = Field(default=15_000_000, ge=1_000_000, le=25_000_000)
    upload_session_hours: int = Field(default=72, ge=1, le=168)
    upload_session_max_files: int = Field(default=20, ge=1, le=50)
    upload_session_max_bytes: int = Field(default=75_000_000, ge=1_000_000, le=250_000_000)
    upload_storage_path: Path = Path("./private-uploads")
    upload_bucket: str = ""
    database_path: Path = Path("./benson-operations.sqlite3")
    database_url: str = ""
    ddc_registry_path: Path = Path("skills/registry.json")
    web_dist_path: Path | None = None

    @model_validator(mode="after")
    def production_is_fail_closed(self) -> "Settings":
        if self.environment != "production":
            return self
        missing: list[str] = []
        if self.website_signing_secret == "development-signing-secret":
            missing.append("BENSON_WEBSITE_SIGNING_SECRET")
        if not self.staff_google_audience:
            missing.append("BENSON_STAFF_GOOGLE_AUDIENCE")
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            missing.append("BENSON_DATABASE_URL (PostgreSQL)")
        if not self.upload_bucket:
            missing.append("BENSON_UPLOAD_BUCKET")
        if self.fcc_base_url.host in {"127.0.0.1", "localhost"}:
            missing.append("BENSON_FCC_BASE_URL (reachable gateway)")
        if missing:
            raise ValueError(f"Production configuration is incomplete: {', '.join(missing)}")
        return self

    def resolved_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("postgresql://"):
                return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.database_url
        return f"sqlite+pysqlite:///{self.database_path.resolve()}"

    def role_emails(self, role: str) -> set[str]:
        raw = getattr(self, f"{role}_emails", "")
        return {email.strip().lower() for email in raw.split(",") if email.strip()}

    def resolved_ddc_registry_path(self) -> Path:
        if self.ddc_registry_path.is_absolute():
            return self.ddc_registry_path
        source = Path(__file__).resolve()
        candidates = [
            Path.cwd() / self.ddc_registry_path,
            source.parents[1] / self.ddc_registry_path,
            source.parents[2] / self.ddc_registry_path,
        ]
        return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


@lru_cache
def get_settings() -> Settings:
    return Settings()
