import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.platform.models import AuditEvent, OutboxEvent


def add_audit(
    session: AsyncSession,
    principal: Principal,
    record_type: str,
    record_id: uuid.UUID,
    action: str,
    correlation_id: uuid.UUID,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    reason: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            record_type=record_type,
            record_id=record_id,
            action=action,
            before_state=before,
            after_state=after,
            correlation_id=correlation_id,
            reason=reason,
        )
    )


def add_outbox(
    session: AsyncSession,
    principal: Principal,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    correlation_id: uuid.UUID,
    idempotency_key: str,
    payload: dict[str, Any],
) -> None:
    session.add(
        OutboxEvent(
            tenant_id=principal.tenant_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
    )
