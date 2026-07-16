from typing import Any

from .config import IntegrationConfigurationError, MetaConfig
from .models import DeliveryCommand, DeliveryResult, IntegrationEvent
from .privacy import hashed_user_data, require_ad_consent, sha256
from .transport import AsyncJsonTransport


def build_meta_event(event: IntegrationEvent) -> dict[str, Any]:
    require_ad_consent(event)
    user_data: dict[str, Any] = hashed_user_data(event)
    user_data["external_id"] = [sha256(event.event_id)]
    if event.fbc:
        user_data["fbc"] = event.fbc
    if event.fbp:
        user_data["fbp"] = event.fbp
    payload: dict[str, Any] = {
        "event_name": event.event_name,
        "event_time": int(event.occurred_at.timestamp()),
        "event_id": event.event_id,
        "action_source": "website",
        "event_source_url": event.source_url,
        "user_data": user_data,
    }
    if event.value is not None:
        payload["custom_data"] = {
            "value": float(event.value),
            "currency": event.currency,
        }
    return payload


class MetaConversionsAdapter:
    def __init__(self, config: MetaConfig, transport: AsyncJsonTransport) -> None:
        self.config = config
        self.transport = transport

    def command(self, event: IntegrationEvent) -> DeliveryCommand:
        return DeliveryCommand(
            provider="meta_capi",
            idempotency_key=event.event_id,
            payload={"data": [build_meta_event(event)]},
        )

    async def publish(self, command: DeliveryCommand) -> DeliveryResult:
        if not self.config.enabled or self.config.dry_run:
            return DeliveryResult("meta_capi", command.idempotency_key, True, False)
        if not self.config.pixel_id or not self.config.access_token:
            raise IntegrationConfigurationError(
                "Meta pixel ID and access token are required"
            )
        response = await self.transport.post(
            f"https://graph.facebook.com/{self.config.api_version}/"
            f"{self.config.pixel_id}/events",
            params={"access_token": self.config.access_token},
            payload=command.payload,
        )
        return DeliveryResult(
            "meta_capi",
            command.idempotency_key,
            False,
            bool(response.get("events_received")),
            str(response.get("fbtrace_id") or "") or None,
        )
