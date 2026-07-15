from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


class NotificationDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeliveryResult:
    provider_message_id: str


def _lead_summary(payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"Name: {payload['name']}",
            f"Phone: {payload['phone']}",
            f"Email: {payload.get('email') or 'Not provided'}",
            f"Service: {payload['service_type']}",
            f"Urgency: {payload['urgency']}",
            f"City: {payload.get('city') or 'Not provided'}",
            "",
            str(payload["message"]),
        )
    )


def deliver_notification(item: dict[str, Any], settings: Settings) -> DeliveryResult:
    payload = item["payload"]
    try:
        if item["channel"] == "email":
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                    "Idempotency-Key": item["id"],
                },
                json={
                    "from": settings.resend_from_email,
                    "to": [item["destination"]],
                    "subject": f"New {payload['urgency']} lead: {payload['name']}",
                    "text": _lead_summary(payload),
                },
                timeout=20,
            )
        elif item["channel"] == "sms":
            response = httpx.post(
                "https://api.twilio.com/2010-04-01/Accounts/"
                f"{settings.twilio_account_sid}/Messages.json",
                auth=(
                    settings.twilio_api_key_sid,
                    settings.twilio_api_key_secret.get_secret_value(),
                ),
                data={
                    "From": settings.twilio_from_number,
                    "To": item["destination"],
                    "Body": (
                        f"EMERGENCY Benson lead: {payload['name']}, {payload['phone']}, "
                        f"{payload['service_type']}, {payload.get('city') or 'location not provided'}."
                    ),
                },
                timeout=20,
            )
        else:
            raise NotificationDeliveryError(f"Unsupported channel: {item['channel']}")
        response.raise_for_status()
    except (httpx.HTTPError, KeyError) as error:
        raise NotificationDeliveryError(str(error)[:1_000]) from error
    body = response.json()
    message_id = str(body.get("id") or body.get("sid") or "")
    if not message_id:
        raise NotificationDeliveryError("Provider response did not include a message ID")
    return DeliveryResult(provider_message_id=message_id)
