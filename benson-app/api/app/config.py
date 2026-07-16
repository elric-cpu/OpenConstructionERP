import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
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
    employee_invite_signing_secret: str = Field(
        default="development-invite-signing-secret", min_length=16
    )
    employee_document_encryption_key: SecretStr = SecretStr("")
    employee_document_key_version: str = "v1"
    website_signature_max_age_seconds: int = Field(default=300, ge=30, le=900)
    staff_google_audience: str = ""
    staff_google_domain: str = "bensonhomesolutions.com"
    owner_emails: str = "office@bensonhomesolutions.com"
    admin_emails: str = ""
    office_emails: str = ""
    estimator_pm_emails: str = ""
    accounting_emails: str = ""
    field_emails: str = ""
    staff_display_names: str = ""
    fcc_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8082")
    fcc_auth_token: str = Field(default="freecc", min_length=1)
    fcc_model: str = "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
    ai_max_steps: int = Field(default=12, ge=1, le=30)
    ai_timeout_seconds: int = Field(default=90, ge=5, le=300)

    notification_worker_audience: AnyHttpUrl | None = None
    notification_worker_email: str = ""
    notification_email_to: str = "office@bensonhomesolutions.com"
    notification_max_attempts: int = Field(default=10, ge=2, le=25)
    notification_batch_size: int = Field(default=25, ge=1, le=100)
    resend_api_key: SecretStr = SecretStr("")
    resend_from_email: str = "Benson Home Solutions <leads@bensonhomesolutions.com>"
    twilio_account_sid: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: SecretStr = SecretStr("")
    twilio_from_number: str = ""
    sms_to: str = ""
    sms_enabled_default: bool = False

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
        if self.employee_invite_signing_secret == "development-invite-signing-secret":
            missing.append("BENSON_EMPLOYEE_INVITE_SIGNING_SECRET")
        try:
            self.employee_document_key_bytes()
        except ValueError:
            missing.append("BENSON_EMPLOYEE_DOCUMENT_ENCRYPTION_KEY (base64 32-byte key)")
        if not self.staff_google_audience:
            missing.append("BENSON_STAFF_GOOGLE_AUDIENCE")
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            missing.append("BENSON_DATABASE_URL (PostgreSQL)")
        if not self.upload_bucket:
            missing.append("BENSON_UPLOAD_BUCKET")
        if self.fcc_base_url.host in {"127.0.0.1", "localhost"}:
            missing.append("BENSON_FCC_BASE_URL (reachable gateway)")
        if not self.notification_worker_audience:
            missing.append("BENSON_NOTIFICATION_WORKER_AUDIENCE")
        if not self.notification_worker_email:
            missing.append("BENSON_NOTIFICATION_WORKER_EMAIL")
        if not self.resend_api_key.get_secret_value():
            missing.append("BENSON_RESEND_API_KEY")
        if not self.notification_email_to:
            missing.append("BENSON_NOTIFICATION_EMAIL_TO")
        if self.sms_enabled_default and not self.twilio_is_configured():
            missing.append("BENSON_TWILIO_* and BENSON_SMS_TO")
        if missing:
            raise ValueError(f"Production configuration is incomplete: {', '.join(missing)}")
        return self

    def resolved_database_url(self) -> str:
        if self.database_url:
            if self.database_url.startswith("postgresql://"):
                return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.database_url
        return f"sqlite+pysqlite:///{self.database_path.resolve()}"

    def employee_document_key_bytes(self) -> bytes:
        raw = self.employee_document_encryption_key.get_secret_value()
        try:
            key = base64.b64decode(raw, validate=True)
        except ValueError as error:
            raise ValueError("Employee document encryption key must be valid base64") from error
        if len(key) != 32:
            raise ValueError("Employee document encryption key must decode to 32 bytes")
        return key

    def role_emails(self, role: str) -> set[str]:
        raw = getattr(self, f"{role}_emails", "")
        return {email.strip().lower() for email in raw.split(",") if email.strip()}

    def staff_name_map(self) -> dict[str, str]:
        names: dict[str, str] = {}
        for entry in self.staff_display_names.split(","):
            email, separator, display_name = entry.partition("=")
            if separator and email.strip() and display_name.strip():
                names[email.strip().lower()] = display_name.strip()
        return names

    def assignable_staff(self) -> list[dict[str, str]]:
        names = self.staff_name_map()
        members: list[dict[str, str]] = []
        seen: set[str] = set()
        for role in ("owner", "admin", "office", "estimator_pm", "field"):
            for email in sorted(self.role_emails(role)):
                if email in seen:
                    continue
                seen.add(email)
                fallback_name = email.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
                members.append(
                    {
                        "email": email,
                        "display_name": names.get(email, fallback_name),
                        "role": role,
                    }
                )
        return members

    def twilio_is_configured(self) -> bool:
        return all(
            (
                self.twilio_account_sid,
                self.twilio_api_key_sid,
                self.twilio_api_key_secret.get_secret_value(),
                self.twilio_from_number,
                self.sms_to,
            )
        )

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
