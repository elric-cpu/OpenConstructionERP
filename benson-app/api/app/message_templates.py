from dataclasses import dataclass
from typing import Any, Literal

MessageAudience = Literal["residential", "federal", "emergency"]


@dataclass(frozen=True)
class ClientMessage:
    audience: MessageAudience
    body: str
    priority: Literal["normal", "high"] = "normal"


def client_lead_message(payload: dict[str, Any]) -> ClientMessage:
    first_name = str(payload.get("name") or "there").strip().split(maxsplit=1)[0]
    if payload.get("urgency") == "emergency":
        return ClientMessage(
            audience="emergency",
            priority="high",
            body=(
                f"Benson Home Solutions received your urgent request, {first_name}. "
                "If anyone is in immediate danger, leave the affected area and call "
                "911. We will validate your callback priority as soon as possible. "
                "Reply with photos only when it is safe to do so."
            ),
        )
    if payload.get("customer_type") == "government_procurement_officer":
        return ClientMessage(
            audience="federal",
            body=(
                "Benson Home Solutions confirms receipt of your procurement inquiry. "
                "The record has been routed to the internal federal-contracting review "
                "queue. Please retain this message with your intake receipt."
            ),
        )
    return ClientMessage(
        audience="residential",
        body=(
            f"Thanks, {first_name}. Benson Home Solutions received your request. "
            "We aim to respond within two business hours. You may reply with project "
            "photos; accepted media will be attached to your protected lead record."
        ),
    )
