from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_ENCRYPTION_KEY = "Ple9DVzO2y3l-lGSmHVEP0_hZFkT8Q53FixYXFveOp8="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = (
        "postgresql+asyncpg://benson_app:benson-app-development-only@postgres/benson_erp"
    )
    migration_database_url: str | None = None
    redis_url: str = "redis://redis:6379/0"
    log_level: str = "INFO"
    metrics_enabled: bool = True
    metrics_bearer_token: SecretStr | None = None
    readiness_timeout_seconds: float = Field(default=2.0, ge=0.1, le=30)
    otel_service_name: str = "benson-erp-api"
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_headers: str | None = None
    otel_trace_sample_ratio: float = Field(default=1.0, ge=0, le=1)
    worker_batch_size: int = Field(default=50, ge=1, le=500)
    worker_lease_seconds: int = Field(default=300, ge=30, le=3600)
    worker_max_attempts: int = Field(default=8, ge=1, le=50)
    worker_retry_base_seconds: int = Field(default=10, ge=1, le=3600)
    worker_retry_max_seconds: int = Field(default=3600, ge=10, le=86400)
    secret_key: str = Field(default="development-only-secret-replace-me", min_length=32)
    encryption_key: str = DEVELOPMENT_ENCRYPTION_KEY
    cors_origins: str = "http://benson-ai:5173"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    storage_backend: str = "local"
    local_storage_root: str = ".data/storage"
    storage_signed_url_seconds: int = Field(default=300, ge=30, le=3600)
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-west-2"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_addressing_style: str = "path"
    s3_server_side_encryption: str | None = None
    gcs_bucket: str | None = None
    gcs_project: str | None = None
    google_directory_provider: str = "disabled"
    google_directory_service_account_json: SecretStr | None = None
    google_directory_delegated_admin: str | None = None
    google_directory_timeout_seconds: float = Field(default=10, ge=1, le=60)
    email_provider: str = "disabled"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str = "Benson Enterprises"
    smtp_tls_mode: str = "starttls"
    smtp_timeout_seconds: float = Field(default=10, ge=1, le=60)
    frontend_url: str = "http://benson-ai:5173"
    employee_activation_hours: int = Field(default=24, ge=1, le=168)
    employee_support_details: str = "Benson Enterprises support: (458) 723-0818"
    web_dist_path: str | None = None

    @model_validator(mode="after")
    def reject_insecure_production(self) -> "Settings":
        try:
            Fernet(self.encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise ValueError("Encryption key must be a valid Fernet key") from exc
        if self.storage_backend not in {"local", "s3", "gcs"}:
            raise ValueError("Storage backend must be local, s3, or gcs")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3 storage requires S3_BUCKET")
        if bool(self.s3_access_key) != bool(self.s3_secret_key):
            raise ValueError("S3 access key and secret key must be configured together")
        if self.storage_backend == "gcs" and not self.gcs_bucket:
            raise ValueError("Google Cloud Storage requires GCS_BUCKET")
        if self.google_directory_provider not in {"disabled", "google", "mock"}:
            raise ValueError("Google Directory provider must be disabled, google, or mock")
        if self.google_directory_provider == "google" and (
            self.google_directory_service_account_json is None
            or not self.google_directory_delegated_admin
        ):
            raise ValueError(
                "Google Directory requires service-account JSON and a delegated administrator"
            )
        if self.email_provider not in {"disabled", "smtp", "mock"}:
            raise ValueError("Email provider must be disabled, smtp, or mock")
        if self.smtp_tls_mode not in {"none", "starttls", "ssl"}:
            raise ValueError("SMTP TLS mode must be none, starttls, or ssl")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP username and password must be configured together")
        if self.email_provider == "smtp" and (not self.smtp_host or not self.smtp_from_email):
            raise ValueError("SMTP email requires SMTP_HOST and SMTP_FROM_EMAIL")
        if self.worker_retry_base_seconds > self.worker_retry_max_seconds:
            raise ValueError("Worker retry base cannot exceed retry maximum")
        if self.environment != "production":
            return self
        insecure = ("development", "replace-me", "benson-development-only")
        serialized = " ".join(
            filter(
                None,
                (
                    self.database_url,
                    self.migration_database_url,
                    self.secret_key,
                    self.encryption_key,
                ),
            )
        )
        if (
            any(marker in serialized for marker in insecure)
            or self.encryption_key == DEVELOPMENT_ENCRYPTION_KEY
        ):
            raise ValueError("Production configuration contains default or insecure secrets")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS is forbidden in production")
        if self.metrics_enabled and self.metrics_bearer_token is None:
            raise ValueError("Production metrics require METRICS_BEARER_TOKEN")
        if self.storage_backend == "local":
            raise ValueError("Local object storage is forbidden in production")
        if self.google_directory_provider == "mock":
            raise ValueError("Mock Google Directory is forbidden in production")
        for endpoint in (self.s3_endpoint_url, self.s3_public_endpoint_url):
            if endpoint and not endpoint.startswith("https://"):
                raise ValueError("Production S3 endpoints must use HTTPS")
        if self.email_provider in {"disabled", "mock"}:
            raise ValueError("Production requires the SMTP email provider")
        if self.smtp_tls_mode == "none":
            raise ValueError("Production SMTP requires TLS")
        if not self.frontend_url.startswith("https://"):
            raise ValueError("Production frontend URL must use HTTPS")
        if not self.web_dist_path:
            raise ValueError("Production requires WEB_DIST_PATH")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
