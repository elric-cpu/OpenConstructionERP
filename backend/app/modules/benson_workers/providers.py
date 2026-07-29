"""Benson provider adapters over upstream email and identity seams."""

from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings
from app.core.email import DeliveryResult, EmailBackend, EmailMessage

RESEND_EMAILS_URL = "https://api.resend.com/emails"
DIRECTORY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user"
DIRECTORY_USERS_URL = "https://admin.googleapis.com/admin/directory/v1/users"


class ResendEmailBackend(EmailBackend):
    name = "resend"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = settings.resend_api_key
        self._from = settings.resend_from
        self._client = client

    async def send(self, message: EmailMessage) -> DeliveryResult:
        if not self._api_key or not self._from:
            return DeliveryResult.failure(self.name, "Resend is not configured")
        payload: dict[str, Any] = {
            "from": message.from_addr or self._from,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html_body,
            "headers": message.headers,
            "tags": [{"name": "category", "value": tag} for tag in message.tags[:8]],
        }
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        if message.attachments:
            payload["attachments"] = [
                {
                    "filename": attachment.filename,
                    "content": base64.b64encode(attachment.content).decode("ascii"),
                }
                for attachment in message.attachments
            ]
        try:
            if self._client is not None:
                response = await self._client.post(
                    RESEND_EMAILS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            else:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        RESEND_EMAILS_URL,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
        except httpx.HTTPError as exc:
            return DeliveryResult.failure(self.name, f"Resend request failed: {exc.__class__.__name__}")
        if response.is_success:
            message_id = response.json().get("id", "accepted")
            return DeliveryResult.success(self.name, str(message_id))
        return DeliveryResult.failure(self.name, f"Resend returned HTTP {response.status_code}")


@dataclass(frozen=True)
class DirectoryIdentityInput:
    primary_email: str
    first_name: str
    last_name: str
    recovery_email: str
    temporary_password: str
    org_unit_path: str = "/"


@dataclass(frozen=True)
class DirectoryIdentity:
    subject_id: str
    primary_email: str


class DirectoryProviderError(RuntimeError):
    """Raised when Directory provisioning is disabled or fails safely."""


class GoogleDirectoryProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.google_directory_enabled:
            raise DirectoryProviderError("Google Directory is disabled")
        if not settings.google_directory_service_account_json or not settings.google_directory_delegated_admin:
            raise DirectoryProviderError("Google Directory credentials are incomplete")
        try:
            self._credentials = json.loads(settings.google_directory_service_account_json)
        except json.JSONDecodeError as exc:
            raise DirectoryProviderError("Google Directory service-account JSON is invalid") from exc
        required = {"client_email", "private_key", "token_uri"}
        if not required <= self._credentials.keys():
            raise DirectoryProviderError("Google Directory service-account JSON is incomplete")
        self._delegated_admin = settings.google_directory_delegated_admin
        self._timeout = settings.google_directory_timeout_seconds
        self._client = client
        self._access_token = ""
        self._access_token_expires = 0.0

    async def create_identity(self, data: DirectoryIdentityInput) -> DirectoryIdentity:
        token = await self._token()
        payload = {
            "primaryEmail": data.primary_email,
            "name": {"givenName": data.first_name, "familyName": data.last_name},
            "password": data.temporary_password,
            "changePasswordAtNextLogin": True,
            "orgUnitPath": data.org_unit_path,
            "recoveryEmail": data.recovery_email,
        }
        response = await self._request("POST", DIRECTORY_USERS_URL, token, json=payload)
        if response.status_code == 409:
            user_url = f"{DIRECTORY_USERS_URL}/{quote(data.primary_email, safe='')}"
            response = await self._request("GET", user_url, token)
        if not response.is_success:
            raise DirectoryProviderError(f"Google Directory returned HTTP {response.status_code}")
        body = response.json()
        if not body.get("id") or not body.get("primaryEmail"):
            raise DirectoryProviderError("Google Directory returned an incomplete identity")
        return DirectoryIdentity(subject_id=str(body["id"]), primary_email=str(body["primaryEmail"]))

    async def _token(self) -> str:
        from jose import jwt

        now = int(time.time())
        if self._access_token and self._access_token_expires > now + 60:
            return self._access_token
        assertion = jwt.encode(
            {
                "iss": self._credentials["client_email"],
                "sub": self._delegated_admin,
                "scope": DIRECTORY_SCOPE,
                "aud": self._credentials["token_uri"],
                "iat": now,
                "exp": now + 3600,
                "jti": str(uuid.uuid4()),
            },
            self._credentials["private_key"],
            algorithm="RS256",
        )
        response = await self._request(
            "POST",
            self._credentials["token_uri"],
            "",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        )
        if not response.is_success or not response.json().get("access_token"):
            raise DirectoryProviderError(f"Google token exchange returned HTTP {response.status_code}")
        body = response.json()
        self._access_token = str(body["access_token"])
        self._access_token_expires = now + int(body.get("expires_in", 3600))
        return self._access_token

    async def _request(self, method: str, url: str, token: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self._client is not None:
            return await self._client.request(method, url, headers=headers, **kwargs)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.request(method, url, headers=headers, **kwargs)


def provider_status(settings: Settings | None = None) -> dict[str, dict[str, bool]]:
    current = settings or get_settings()
    return {
        "resend": {
            "enabled": current.email_backend == "resend",
            "configured": bool(current.resend_api_key and current.resend_from),
        },
        "google_directory": {
            "enabled": current.google_directory_enabled,
            "configured": bool(
                current.google_directory_service_account_json and current.google_directory_delegated_admin
            ),
        },
    }
