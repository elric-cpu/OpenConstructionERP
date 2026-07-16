import asyncio
from collections.abc import Sequence
from typing import Any, cast

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from .config import GoogleCredentialConfig, IntegrationConfigurationError


def google_credentials(
    config: GoogleCredentialConfig, scopes: Sequence[str]
) -> Credentials:
    credential_factory = cast(Any, service_account.Credentials)
    if config.service_account_json:
        return cast(
            Credentials,
            credential_factory.from_service_account_info(
                config.service_account_json, scopes=scopes
            ),
        )
    if config.service_account_file:
        return cast(
            Credentials,
            credential_factory.from_service_account_file(
                config.service_account_file, scopes=scopes
            ),
        )
    credentials, _project = google.auth.default(scopes=scopes)
    if not credentials:
        raise IntegrationConfigurationError("Google ADC did not provide credentials")
    return credentials


async def google_access_token(credentials: Credentials) -> str:
    if not credentials.valid or not credentials.token:
        await asyncio.to_thread(credentials.refresh, Request())
    if not credentials.token:
        raise IntegrationConfigurationError("Google credentials did not issue a token")
    return cast(str, credentials.token)
