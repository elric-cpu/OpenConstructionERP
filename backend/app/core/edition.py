"""Edition-specific policy helpers that leave the upstream runtime intact."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BENSON_EDITION = "benson"
BENSON_REGION = "benson_eastern_oregon"
PROJECT_CONTEXT_KEYS = ("county", "local_jurisdiction", "timezone")


def is_benson_edition() -> bool:
    from app.config import get_settings

    return get_settings().edition.strip().lower() == BENSON_EDITION


def supported_locale_codes() -> frozenset[str]:
    from app.config import get_settings

    raw = get_settings().supported_locales
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def validate_locale(locale: str | None) -> str | None:
    if locale is None:
        return None
    cleaned = locale.strip()
    if not cleaned:
        raise ValueError("Locale cannot be empty")
    supported = supported_locale_codes()
    if supported and cleaned.lower() not in supported and cleaned.split("-", 1)[0].lower() not in supported:
        raise ValueError(f"Unsupported locale '{cleaned}'. Supported locales: {', '.join(sorted(supported))}")
    return cleaned


def normalize_project_context(
    county: str | None,
    local_jurisdiction: str | None,
    timezone: str | None,
    *,
    required: bool | None = None,
) -> dict[str, str]:
    values = {
        "county": (county or "").strip(),
        "local_jurisdiction": (local_jurisdiction or "").strip(),
        "timezone": (timezone or "").strip(),
    }
    must_supply = is_benson_edition() if required is None else required
    if must_supply:
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError(f"Benson projects require: {', '.join(missing)}")
    if values["timezone"]:
        try:
            ZoneInfo(values["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone '{values['timezone']}'") from exc
    return {key: value for key, value in values.items() if value}


def validate_project_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_project_context(
        str(metadata.get("county") or ""),
        str(metadata.get("local_jurisdiction") or ""),
        str(metadata.get("timezone") or ""),
    )
    result = dict(metadata)
    result.update(normalized)
    return result
