from typing import Any

from .config import GoogleBusinessConfig, IntegrationConfigurationError
from .models import DeliveryCommand, DeliveryResult
from .transport import AsyncJsonTransport


def build_local_post(summary: str, link_url: str | None = None) -> dict[str, Any]:
    clean_summary = " ".join(summary.split())
    if not clean_summary or len(clean_summary) > 1_500:
        raise ValueError("Business Profile post summary must be 1-1500 characters")
    payload: dict[str, Any] = {
        "languageCode": "en-US",
        "summary": clean_summary,
        "topicType": "STANDARD",
    }
    if link_url:
        if not link_url.startswith("https://"):
            raise ValueError("Business Profile call-to-action URL must use HTTPS")
        payload["callToAction"] = {"actionType": "LEARN_MORE", "url": link_url}
    return payload


class GoogleBusinessProfileAdapter:
    """GBP publishing requires owner/user OAuth, never service-account ADC."""

    def __init__(
        self, config: GoogleBusinessConfig, transport: AsyncJsonTransport
    ) -> None:
        self.config = config
        self.transport = transport

    def command(
        self, *, idempotency_key: str, summary: str, link_url: str | None = None
    ) -> DeliveryCommand:
        return DeliveryCommand(
            "google_business_profile",
            idempotency_key,
            build_local_post(summary, link_url),
        )

    async def publish(self, command: DeliveryCommand) -> DeliveryResult:
        if not self.config.enabled or self.config.dry_run:
            return DeliveryResult(
                "google_business_profile", command.idempotency_key, True, False
            )
        if not self.config.user_access_token:
            raise IntegrationConfigurationError(
                "Google Business Profile posts require business-owner user OAuth "
                "with business.manage consent; service-account/ADC credentials cannot "
                "substitute for that grant"
            )
        if not self.config.account_id or not self.config.location_id:
            raise IntegrationConfigurationError(
                "GBP account and location IDs are required"
            )
        response = await self.transport.post(
            "https://mybusiness.googleapis.com/v4/accounts/"
            f"{self.config.account_id}/locations/{self.config.location_id}/localPosts",
            headers={"authorization": f"Bearer {self.config.user_access_token}"},
            payload=command.payload,
        )
        return DeliveryResult(
            "google_business_profile",
            command.idempotency_key,
            False,
            bool(response.get("name")),
            str(response.get("name") or "") or None,
        )
