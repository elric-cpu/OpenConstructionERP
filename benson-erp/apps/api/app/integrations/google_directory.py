import json
import uuid
from asyncio import to_thread
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from app.core.config import Settings

DIRECTORY_SCOPE = "https://www.googleapis.com/auth/admin.directory.user"
DIRECTORY_USERS_URL = "https://admin.googleapis.com/admin/directory/v1/users"


class DirectoryProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class DirectoryIdentityInput:
    primary_email: str
    first_name: str
    last_name: str
    recovery_email: str
    org_unit_path: str
    temporary_password: str


@dataclass(frozen=True)
class DirectoryIdentity:
    subject_id: str
    primary_email: str


class DirectoryProvider(Protocol):
    async def create_identity(self, data: DirectoryIdentityInput) -> DirectoryIdentity: ...


class DisabledDirectoryProvider:
    async def create_identity(self, data: DirectoryIdentityInput) -> DirectoryIdentity:
        del data
        raise DirectoryProviderError("Google Directory provisioning is not configured")


class MockDirectoryProvider:
    async def create_identity(self, data: DirectoryIdentityInput) -> DirectoryIdentity:
        return DirectoryIdentity(
            subject_id=str(uuid.uuid5(uuid.NAMESPACE_URL, data.primary_email)),
            primary_email=data.primary_email,
        )


class GoogleDirectoryProvider:
    def __init__(self, settings: Settings) -> None:
        secret = settings.google_directory_service_account_json
        if secret is None or not settings.google_directory_delegated_admin:
            raise DirectoryProviderError("Google Directory credentials are incomplete")
        try:
            service_account_info = json.loads(secret.get_secret_value())
        except (TypeError, json.JSONDecodeError) as exc:
            raise DirectoryProviderError("Google Directory service-account JSON is invalid") from exc
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[DIRECTORY_SCOPE],
        ).with_subject(settings.google_directory_delegated_admin)
        self._session = AuthorizedSession(credentials)
        self._timeout = settings.google_directory_timeout_seconds

    async def create_identity(self, data: DirectoryIdentityInput) -> DirectoryIdentity:
        return await to_thread(self._create_identity, data)

    def _create_identity(self, data: DirectoryIdentityInput) -> DirectoryIdentity:
        response = self._session.post(
            DIRECTORY_USERS_URL,
            json={
                "primaryEmail": data.primary_email,
                "name": {
                    "givenName": data.first_name,
                    "familyName": data.last_name,
                },
                "password": data.temporary_password,
                "changePasswordAtNextLogin": True,
                "orgUnitPath": data.org_unit_path,
                "recoveryEmail": data.recovery_email,
            },
            timeout=self._timeout,
        )
        if response.status_code == 409:
            response = self._session.get(
                f"{DIRECTORY_USERS_URL}/{quote(data.primary_email, safe='')}",
                timeout=self._timeout,
            )
        if not response.ok:
            raise DirectoryProviderError(
                f"Google Directory user operation failed with status {response.status_code}"
            )
        payload = response.json()
        subject_id = payload.get("id")
        primary_email = payload.get("primaryEmail")
        if not subject_id or not primary_email:
            raise DirectoryProviderError("Google Directory returned an incomplete user")
        return DirectoryIdentity(subject_id=str(subject_id), primary_email=str(primary_email))


def build_directory_provider(settings: Settings) -> DirectoryProvider:
    if settings.google_directory_provider == "google":
        return GoogleDirectoryProvider(settings)
    if settings.google_directory_provider == "mock":
        return MockDirectoryProvider()
    return DisabledDirectoryProvider()
