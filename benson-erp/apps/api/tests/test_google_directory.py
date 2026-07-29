import pytest
from app.core.config import Settings
from app.integrations.google_directory import (
    DirectoryIdentityInput,
    GoogleDirectoryProvider,
    MockDirectoryProvider,
)
from pydantic import ValidationError


@pytest.mark.asyncio
async def test_mock_directory_identity_is_idempotent() -> None:
    provider = MockDirectoryProvider()
    data = _identity_input()

    first = await provider.create_identity(data)
    second = await provider.create_identity(data)

    assert first == second
    assert first.primary_email == data.primary_email


def test_google_directory_create_forces_password_change_and_recovers_conflict() -> None:
    provider = object.__new__(GoogleDirectoryProvider)
    session = FakeSession()
    provider._session = session
    provider._timeout = 10

    identity = provider._create_identity(_identity_input())

    assert identity.subject_id == "google-subject"
    assert identity.primary_email == "ada@bensonhomesolutions.com"
    assert session.created_payload["changePasswordAtNextLogin"] is True
    assert session.created_payload["orgUnitPath"] == "/Employees"
    assert session.created_payload["recoveryEmail"] == "ada@example.com"
    assert session.get_url.endswith("ada%40bensonhomesolutions.com")


def test_google_directory_configuration_is_fail_closed() -> None:
    with pytest.raises(ValidationError, match="service-account JSON"):
        Settings(google_directory_provider="google")
    with pytest.raises(ValidationError, match="Mock Google Directory"):
        Settings(
            environment="production",
            database_url="postgresql+asyncpg://runtime:strong-password@database/erp",
            secret_key="a-secure-production-secret-over-thirty-two-characters",
            encryption_key="ctbR04iysWmDsfNbAwVWACbVSjLnSXam4tK_2mE6b5Y=",
            metrics_bearer_token="metrics-secret",
            storage_backend="gcs",
            gcs_bucket="secure-private-bucket",
            google_directory_provider="mock",
        )


def _identity_input() -> DirectoryIdentityInput:
    return DirectoryIdentityInput(
        primary_email="ada@bensonhomesolutions.com",
        first_name="Ada",
        last_name="Builder",
        recovery_email="ada@example.com",
        org_unit_path="/Employees",
        temporary_password="temporary-secret-never-email",
    )


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.created_payload: dict = {}
        self.get_url = ""

    def post(self, url: str, *, json: dict, timeout: float) -> FakeResponse:
        del url, timeout
        self.created_payload = json
        return FakeResponse(409)

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        del timeout
        self.get_url = url
        return FakeResponse(
            200,
            {
                "id": "google-subject",
                "primaryEmail": "ada@bensonhomesolutions.com",
            },
        )
