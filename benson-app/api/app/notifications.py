from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .message_templates import client_lead_message
from .signing import employee_invite_token


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


def _email_message(payload: dict[str, Any], settings: Settings) -> tuple[str, str]:
    if payload.get("kind") == "employee_invitation":
        token = employee_invite_token(
            settings.employee_invite_signing_secret, str(payload["invite_id"])
        )
        invite_url = f"{payload['invite_base_url']}/#/activate?token={token}"
        return (
            "Your Benson Home Solutions staff portal invitation",
            "\n".join(
                (
                    f"Hello {payload['name']},",
                    "",
                    "Benson Home Solutions invited you to set up your staff portal account.",
                    f"Open this secure invitation before {payload['expires_at']}:",
                    invite_url,
                    "",
                    "If you were not expecting this invitation, do not use the link.",
                )
            ),
        )
    return f"New {payload['urgency']} lead: {payload['name']}", _lead_summary(payload)


def deliver_notification(item: dict[str, Any], settings: Settings) -> DeliveryResult:
    payload = item["payload"]
    try:
        if item["channel"] == "email":
            subject, text = _email_message(payload, settings)
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                    "Idempotency-Key": item["id"],
                },
                json={
                    "from": settings.resend_from_email,
                    "to": [item["destination"]],
                    "subject": subject,
                    "text": text,
                },
                timeout=20,
            )
        elif item["channel"] == "sms":
            sms_body = (
                client_lead_message(payload).body
                if payload.get("kind") == "client_lead_acknowledgement"
                else (
                    f"EMERGENCY Benson lead: {payload['name']}, {payload['phone']}, "
                    f"{payload['service_type']}, "
                    f"{payload.get('city') or 'location not provided'}."
                )
            )
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
                    "Body": sms_body,
                },
                timeout=20,
            )
        else:
            raise NotificationDeliveryError(f"Unsupported channel: {item['channel']}")
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise NotificationDeliveryError(str(error)[:1_000]) from error
    message_id = str(body.get("id") or body.get("sid") or "")
    if not message_id:
        raise NotificationDeliveryError(
            "Provider response did not include a message ID"
        )
    return DeliveryResult(provider_message_id=message_id)
