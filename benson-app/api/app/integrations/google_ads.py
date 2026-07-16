from typing import Any

from google.auth.credentials import Credentials

from .config import GoogleAdsConfig, IntegrationConfigurationError
from .google_auth import google_access_token
from .models import DeliveryCommand, DeliveryResult, IntegrationEvent
from .privacy import hashed_user_data, require_ad_consent, sha256
from .transport import AsyncJsonTransport


def build_offline_conversion(
    event: IntegrationEvent, conversion_action: str
) -> dict[str, Any]:
    require_ad_consent(event)
    identifiers = []
    user_data = hashed_user_data(event)
    if "em" in user_data:
        identifiers.append({"hashedEmail": user_data["em"][0]})
    if "ph" in user_data:
        identifiers.append({"hashedPhoneNumber": user_data["ph"][0]})
    conversion: dict[str, Any] = {
        "conversionAction": conversion_action,
        "conversionDateTime": event.occurred_at.isoformat(sep=" ", timespec="seconds"),
        "orderId": sha256(event.event_id),
        "currencyCode": event.currency,
        "consent": {"adUserData": "GRANTED"},
        "userIdentifiers": identifiers[:5],
    }
    if event.gclid:
        conversion["gclid"] = event.gclid
    if event.value is not None:
        conversion["conversionValue"] = float(event.value)
    return conversion


class GoogleAdsAdapter:
    scope = "https://www.googleapis.com/auth/adwords"

    def __init__(
        self,
        config: GoogleAdsConfig,
        credentials: Credentials,
        transport: AsyncJsonTransport,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.transport = transport

    def command(self, event: IntegrationEvent) -> DeliveryCommand:
        if not self.config.conversion_action:
            raise IntegrationConfigurationError(
                "Google Ads conversion action is required"
            )
        return DeliveryCommand(
            provider="google_ads",
            idempotency_key=event.event_id,
            payload={
                "conversions": [
                    build_offline_conversion(event, self.config.conversion_action)
                ],
                "partialFailure": True,
            },
        )

    async def publish(self, command: DeliveryCommand) -> DeliveryResult:
        if not self.config.enabled or self.config.dry_run:
            return DeliveryResult("google_ads", command.idempotency_key, True, False)
        required = {
            "customer ID": self.config.customer_id,
            "developer token": self.config.developer_token,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise IntegrationConfigurationError(
                f"Google Ads missing {', '.join(missing)}"
            )
        token = await google_access_token(self.credentials)
        headers = {
            "authorization": f"Bearer {token}",
            "developer-token": str(self.config.developer_token),
        }
        if self.config.login_customer_id:
            headers["login-customer-id"] = self.config.login_customer_id
        response = await self.transport.post(
            f"https://googleads.googleapis.com/{self.config.api_version}/customers/"
            f"{self.config.customer_id}:uploadClickConversions",
            headers=headers,
            payload=command.payload,
        )
        failures = response.get("partialFailureError")
        return DeliveryResult(
            "google_ads", command.idempotency_key, False, not bool(failures)
        )
