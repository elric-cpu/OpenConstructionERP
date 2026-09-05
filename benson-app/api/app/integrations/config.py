import json
import os
from dataclasses import dataclass
from typing import Mapping


class IntegrationConfigurationError(RuntimeError):
    pass


def _enabled(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "false").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class GoogleCredentialConfig:
    service_account_file: str | None
    service_account_json: dict[str, object] | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "GoogleCredentialConfig":
        raw = env.get("BENSON_GOOGLE_SERVICE_ACCOUNT_JSON")
        parsed: dict[str, object] | None = None
        if raw:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as error:
                raise IntegrationConfigurationError(
                    "BENSON_GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON"
                ) from error
            if not isinstance(value, dict):
                raise IntegrationConfigurationError(
                    "Google credential JSON must be an object"
                )
            parsed = value
        return cls(env.get("BENSON_GOOGLE_SERVICE_ACCOUNT_FILE"), parsed)


@dataclass(frozen=True)
class GoogleAdsConfig:
    enabled: bool
    dry_run: bool
    customer_id: str | None
    login_customer_id: str | None
    developer_token: str | None
    conversion_action: str | None
    api_version: str = "v24"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "GoogleAdsConfig":
        return cls(
            _enabled(env, "BENSON_GOOGLE_ADS_ENABLED"),
            not _enabled(env, "BENSON_GOOGLE_ADS_LIVE"),
            env.get("BENSON_GOOGLE_ADS_CUSTOMER_ID"),
            env.get("BENSON_GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
            env.get("BENSON_GOOGLE_ADS_DEVELOPER_TOKEN"),
            env.get("BENSON_GOOGLE_ADS_CONVERSION_ACTION"),
        )


@dataclass(frozen=True)
class MetaConfig:
    enabled: bool
    dry_run: bool
    pixel_id: str | None
    access_token: str | None
    api_version: str = "v23.0"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "MetaConfig":
        return cls(
            _enabled(env, "BENSON_META_CAPI_ENABLED"),
            not _enabled(env, "BENSON_META_CAPI_LIVE"),
            env.get("BENSON_META_PIXEL_ID"),
            env.get("BENSON_META_ACCESS_TOKEN"),
        )


@dataclass(frozen=True)
class GoogleBusinessConfig:
    enabled: bool
    dry_run: bool
    account_id: str | None
    location_id: str | None
    user_access_token: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "GoogleBusinessConfig":
        return cls(
            _enabled(env, "BENSON_GBP_ENABLED"),
            not _enabled(env, "BENSON_GBP_LIVE"),
            env.get("BENSON_GBP_ACCOUNT_ID"),
            env.get("BENSON_GBP_LOCATION_ID"),
            env.get("BENSON_GBP_USER_OAUTH_ACCESS_TOKEN"),
        )
