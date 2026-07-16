from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol


class ConsentStatus(StrEnum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IntegrationEvent:
    event_id: str
    event_name: str
    occurred_at: datetime
    source_url: str
    consent: ConsentStatus
    email: str | None = None
    phone: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    gclid: str | None = None
    fbc: str | None = None
    fbp: str | None = None
    value: Decimal | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class DeliveryCommand:
    provider: str
    idempotency_key: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    idempotency_key: str
    dry_run: bool
    accepted: bool
    provider_id: str | None = None


class OutboxPublisher(Protocol):
    async def publish(self, command: DeliveryCommand) -> DeliveryResult: ...
