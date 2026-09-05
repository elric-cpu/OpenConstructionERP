import html
import smtplib
import ssl
from asyncio import to_thread
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

from app.core.config import Settings


class EmailProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActivationEmailInput:
    personal_email: str
    company_username: str
    google_sign_in_url: str
    erp_sign_in_url: str
    activation_url: str
    expires_at: datetime
    support_details: str
    gmail_unlicensed_statement: str


class EmailProvider(Protocol):
    async def send_activation_email(self, data: ActivationEmailInput) -> None: ...


class DisabledEmailProvider:
    async def send_activation_email(self, data: ActivationEmailInput) -> None:
        del data
        raise EmailProviderError("Email delivery is not configured")


class MockEmailProvider:
    def __init__(self) -> None:
        self.sent: list[ActivationEmailInput] = []

    async def send_activation_email(self, data: ActivationEmailInput) -> None:
        self.sent.append(data)


class SmtpEmailProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise EmailProviderError("SMTP configuration is incomplete")
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = (
            settings.smtp_password.get_secret_value() if settings.smtp_password else None
        )
        self._from_email = settings.smtp_from_email
        self._from_name = settings.smtp_from_name
        self._tls_mode = settings.smtp_tls_mode
        self._timeout = settings.smtp_timeout_seconds

    async def send_activation_email(self, data: ActivationEmailInput) -> None:
        await to_thread(self._send_activation_email, data)

    def _send_activation_email(self, data: ActivationEmailInput) -> None:
        message = self._build_activation_message(data)
        context = ssl.create_default_context()
        try:
            if self._tls_mode == "ssl":
                with smtplib.SMTP_SSL(
                    self._host, self._port, timeout=self._timeout, context=context
                ) as client:
                    self._authenticate_and_send(client, message)
                return
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as client:
                if self._tls_mode == "starttls":
                    client.starttls(context=context)
                self._authenticate_and_send(client, message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailProviderError("Activation email delivery failed") from exc

    def _authenticate_and_send(self, client: smtplib.SMTP, message: EmailMessage) -> None:
        if self._username and self._password:
            client.login(self._username, self._password)
        client.send_message(message)

    def _build_activation_message(self, data: ActivationEmailInput) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = "Activate your Benson Construction ERP access"
        message["From"] = formataddr((self._from_name, self._from_email))
        message["To"] = data.personal_email
        expiry = data.expires_at.isoformat()
        message.set_content(
            "\n".join(
                (
                    "Your Benson Construction ERP access is ready.",
                    "",
                    f"Company username: {data.company_username}",
                    f"Google sign-in: {data.google_sign_in_url}",
                    f"ERP sign-in: {data.erp_sign_in_url}",
                    f"Activate ERP access: {data.activation_url}",
                    f"Activation expires: {expiry}",
                    "",
                    data.gmail_unlicensed_statement,
                    f"Support: {data.support_details}",
                    "",
                    "No permanent password is included in this email.",
                )
            )
        )
        message.add_alternative(
            self._activation_html(data, expiry),
            subtype="html",
        )
        return message

    def _activation_html(self, data: ActivationEmailInput, expiry: str) -> str:
        values = {
            "username": html.escape(data.company_username),
            "google_url": html.escape(data.google_sign_in_url, quote=True),
            "erp_url": html.escape(data.erp_sign_in_url, quote=True),
            "activation_url": html.escape(data.activation_url, quote=True),
            "expiry": html.escape(expiry),
            "statement": html.escape(data.gmail_unlicensed_statement),
            "support": html.escape(data.support_details),
        }
        return (
            "<h1>Your ERP access is ready</h1>"
            f"<p><strong>Company username:</strong> {values['username']}</p>"
            f"<p><a href=\"{values['google_url']}\">Sign in to Google</a></p>"
            f"<p><a href=\"{values['activation_url']}\">Activate ERP access</a></p>"
            f"<p><a href=\"{values['erp_url']}\">Open the ERP sign-in page</a></p>"
            f"<p>Activation expires: {values['expiry']}</p>"
            f"<p>{values['statement']}</p>"
            f"<p>Support: {values['support']}</p>"
            "<p>No permanent password is included in this email.</p>"
        )


def build_email_provider(settings: Settings) -> EmailProvider:
    if settings.email_provider == "smtp":
        return SmtpEmailProvider(settings)
    if settings.email_provider == "mock":
        return MockEmailProvider()
    return DisabledEmailProvider()
