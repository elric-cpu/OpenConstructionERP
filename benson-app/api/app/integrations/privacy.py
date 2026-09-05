import hashlib
import re

from .models import ConsentStatus, IntegrationEvent


class ConsentRequired(ValueError):
    pass


def require_ad_consent(event: IntegrationEvent) -> None:
    if event.consent is not ConsentStatus.GRANTED:
        raise ConsentRequired(
            "Advertising user-data consent must be explicitly granted"
        )


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    local, separator, domain = email.partition("@")
    if separator and domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+", 1)[0].replace(".", "")
    return normalize_text(f"{local}{separator}{domain}")


def hashed_user_data(event: IntegrationEvent) -> dict[str, list[str]]:
    require_ad_consent(event)
    candidates = {
        "em": normalize_email(event.email) if event.email else None,
        "ph": normalize_text(event.phone) if event.phone else None,
        "fn": normalize_text(event.first_name) if event.first_name else None,
        "ln": normalize_text(event.last_name) if event.last_name else None,
        "ct": normalize_text(event.city) if event.city else None,
        "st": normalize_text(event.state) if event.state else None,
        "zp": normalize_text(event.postal_code) if event.postal_code else None,
        "country": normalize_text(event.country_code) if event.country_code else None,
    }
    return {key: [sha256(value)] for key, value in candidates.items() if value}
