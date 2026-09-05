from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.people.events import (
    EMPLOYEE_ACTIVATION_REQUESTED,
    EMPLOYEE_PROVISIONING_REQUESTED,
    GOOGLE_IDENTITY_CREATED,
)
from app.modules.people.handlers import (
    handle_employee_activation_requested,
    handle_employee_provisioning_requested,
    handle_google_identity_created,
)
from app.modules.platform.models import OutboxEvent

Handler = Callable[[AsyncSession, OutboxEvent], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class RegisteredHandler:
    name: str
    callback: Handler


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, list[RegisteredHandler]] = {}

    def register(self, event_type: str, name: str, callback: Handler) -> None:
        handlers = self._handlers.setdefault(event_type, [])
        if any(handler.name == name for handler in handlers):
            raise ValueError(f"Handler {name} already registered for {event_type}")
        handlers.append(RegisteredHandler(name, callback))

    def resolve(self, event_type: str) -> tuple[RegisteredHandler, ...]:
        try:
            return tuple(self._handlers[event_type])
        except KeyError as exc:
            raise LookupError(f"No handler registered for {event_type}") from exc


async def record_domain_event(
    session: AsyncSession, event: OutboxEvent
) -> dict[str, Any]:
    del session
    return {
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
    }


def build_default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    for event_type in (
        "LeadCreated",
        "LeadConverted",
        "EstimateApproved",
        "EmployeeCreated",
        "EmployeeProvisioningRequested",
        "GoogleIdentityCreated",
        "EmployeeActivationRequested",
        "EmployeeActivationSent",
        "EmployeeActivated",
        "EmployeeActivationRevoked",
        "ProposalAccepted",
        "ProjectCreated",
    ):
        registry.register(event_type, "record-domain-event", record_domain_event)
    registry.register(
        EMPLOYEE_PROVISIONING_REQUESTED,
        "provision-google-identity",
        handle_employee_provisioning_requested,
    )
    registry.register(
        GOOGLE_IDENTITY_CREATED,
        "issue-employee-activation",
        handle_google_identity_created,
    )
    registry.register(
        EMPLOYEE_ACTIVATION_REQUESTED,
        "send-employee-activation",
        handle_employee_activation_requested,
    )
    return registry


default_registry = build_default_registry()
