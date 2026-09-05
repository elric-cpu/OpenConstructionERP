import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_production_rejects_default_credentials() -> None:
    with pytest.raises(ValidationError, match="default or insecure"):
        Settings(environment="production")


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://runtime:strong-password@database/erp",
            secret_key="a-secure-production-secret-over-thirty-two-characters",
            encryption_key="ctbR04iysWmDsfNbAwVWACbVSjLnSXam4tK_2mE6b5Y=",
            cors_origins="*",
            storage_backend="gcs",
            gcs_bucket="secure-private-bucket",
            metrics_bearer_token="metrics-secret",
        )


def test_storage_provider_requires_bucket() -> None:
    with pytest.raises(ValidationError, match="S3 storage requires"):
        Settings(storage_backend="s3")
    with pytest.raises(ValidationError, match="Google Cloud Storage requires"):
        Settings(storage_backend="gcs")


def test_google_directory_provider_requires_delegated_credentials() -> None:
    with pytest.raises(ValidationError, match="service-account JSON"):
        Settings(google_directory_provider="google")


def test_production_rejects_local_storage_and_insecure_s3_endpoint() -> None:
    secure = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://runtime:strong-password@database/erp",
        "secret_key": "a-secure-production-secret-over-thirty-two-characters",
        "encryption_key": "ctbR04iysWmDsfNbAwVWACbVSjLnSXam4tK_2mE6b5Y=",
        "metrics_bearer_token": "metrics-secret",
    }
    with pytest.raises(ValidationError, match="Local object storage"):
        Settings(**secure)
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            **secure,
            storage_backend="s3",
            s3_bucket="private",
            s3_endpoint_url="http://objects.internal",
        )


def test_production_requires_metrics_authentication() -> None:
    with pytest.raises(ValidationError, match="metrics require"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://runtime:strong-password@database/erp",
            secret_key="a-secure-production-secret-over-thirty-two-characters",
            encryption_key="ctbR04iysWmDsfNbAwVWACbVSjLnSXam4tK_2mE6b5Y=",
            storage_backend="gcs",
            gcs_bucket="secure-private-bucket",
        )
