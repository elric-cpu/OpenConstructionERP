from collections.abc import Callable
from datetime import UTC, datetime
from email.message import EmailMessage

import pytest
from app.core.config import Settings
from app.integrations.email import (
    ActivationEmailInput,
    DisabledEmailProvider,
    EmailProviderError,
    MockEmailProvider,
    SmtpEmailProvider,
    build_email_provider,
)
from pydantic import SecretStr, ValidationError


@pytest.mark.asyncio
async def test_mock_provider_captures_activation_input_in_memory() -> None:
    provider = MockEmailProvider()
    data = _activation_input()

    await provider.send_activation_email(data)

    assert provider.sent == [data]


@pytest.mark.asyncio
async def test_disabled_provider_fails_closed() -> None:
    provider = DisabledEmailProvider()

    with pytest.raises(EmailProviderError, match="not configured"):
        await provider.send_activation_email(_activation_input())


def test_smtp_provider_builds_complete_activation_message() -> None:
    provider = SmtpEmailProvider(_smtp_settings())

    message = provider._build_activation_message(_activation_input())

    plain = message.get_body(preferencelist=("plain",))
    assert plain is not None
    body = plain.get_content()
    assert message["To"] == "ada@example.com"
    assert "ada.builder" in body
    assert "https://accounts.google.com/" in body
    assert "https://erp.example.com/login" in body
    assert "https://erp.example.com/activate?token=secret" in body
    assert "Gmail may be unavailable" in body
    assert "No permanent password" in body


@pytest.mark.asyncio
async def test_smtp_provider_uses_starttls_and_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeSmtp()
    delegated: list[object] = []

    async def run_inline(
        function: Callable[[ActivationEmailInput], None], data: ActivationEmailInput
    ) -> None:
        delegated.append(function)
        function(data)

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", lambda *args, **kwargs: client)
    monkeypatch.setattr("app.integrations.email.to_thread", run_inline)
    provider = SmtpEmailProvider(_smtp_settings())

    await provider.send_activation_email(_activation_input())

    assert client.started_tls
    assert client.credentials == ("smtp-user", "smtp-secret")
    assert isinstance(client.message, EmailMessage)
    assert delegated == [provider._send_activation_email]


def test_email_configuration_is_fail_closed_in_production() -> None:
    with pytest.raises(ValidationError, match="requires SMTP_HOST"):
        Settings(email_provider="smtp")
    with pytest.raises(ValidationError, match="requires the SMTP"):
        _production_settings(email_provider="mock")
    with pytest.raises(ValidationError, match="requires TLS"):
        _production_settings(email_provider="smtp", smtp_tls_mode="none")


def test_provider_factory_selects_configured_adapter() -> None:
    assert isinstance(build_email_provider(Settings()), DisabledEmailProvider)
    assert isinstance(build_email_provider(Settings(email_provider="mock")), MockEmailProvider)
    assert isinstance(build_email_provider(_smtp_settings()), SmtpEmailProvider)


def _activation_input() -> ActivationEmailInput:
    return ActivationEmailInput(
        personal_email="ada@example.com",
        company_username="ada.builder",
        google_sign_in_url="https://accounts.google.com/",
        erp_sign_in_url="https://erp.example.com/login",
        activation_url="https://erp.example.com/activate?token=secret",
        expires_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        support_details="Call (458) 723-0818",
        gmail_unlicensed_statement="Gmail may be unavailable while this identity is unlicensed.",
    )


def _smtp_settings() -> Settings:
    return Settings(
        email_provider="smtp",
        smtp_host="smtp.example.com",
        smtp_username="smtp-user",
        smtp_password=SecretStr("smtp-secret"),
        smtp_from_email="operations@example.com",
    )


def _production_settings(*, email_provider: str, smtp_tls_mode: str = "starttls") -> Settings:
    return Settings(
        environment="production",
        database_url="postgresql+asyncpg://runtime:strong-password@database/erp",
        secret_key="a-secure-production-secret-over-thirty-two-characters",
        encryption_key="ctbR04iysWmDsfNbAwVWACbVSjLnSXam4tK_2mE6b5Y=",
        metrics_bearer_token=SecretStr("metrics-secret"),
        storage_backend="gcs",
        gcs_bucket="secure-private-bucket",
        email_provider=email_provider,
        smtp_host="smtp.example.com",
        smtp_from_email="operations@example.com",
        smtp_tls_mode=smtp_tls_mode,
    )


class FakeSmtp:
    def __init__(self) -> None:
        self.started_tls = False
        self.credentials: tuple[str, str] | None = None
        self.message: EmailMessage | None = None

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self, *, context: object) -> None:
        del context
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def send_message(self, message: EmailMessage) -> None:
        self.message = message
