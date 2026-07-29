import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionFactory
from app.core.tenancy import set_tenant_context
from app.modules.platform.models import InboxReceipt, OutboxEvent, OutboxStatus
from app.workers.registry import HandlerRegistry, default_registry


class ProcessingOutcome(StrEnum):
    PUBLISHED = "PUBLISHED"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    DEAD_LETTER = "DEAD_LETTER"
    NOT_FOUND = "NOT_FOUND"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


@dataclass(frozen=True)
class ProcessingResult:
    outcome: ProcessingOutcome
    attempt_count: int


def retry_delay_seconds(attempt_count: int, base_seconds: int, max_seconds: int) -> int:
    exponent = max(attempt_count - 1, 0)
    return min(base_seconds * (2**exponent), max_seconds)


async def process_event(
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    registry: HandlerRegistry = default_registry,
) -> ProcessingResult:
    try:
        return await _process_event(tenant_id, event_id, registry)
    except Exception as exc:
        return await record_failure(tenant_id, event_id, exc)


async def _process_event(
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    registry: HandlerRegistry,
) -> ProcessingResult:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        event = await session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.id == event_id,
            )
            .with_for_update()
        )
        if event is None:
            return ProcessingResult(ProcessingOutcome.NOT_FOUND, 0)
        if event.status is OutboxStatus.PUBLISHED:
            return ProcessingResult(ProcessingOutcome.ALREADY_PUBLISHED, event.attempt_count)
        if event.status is OutboxStatus.DEAD_LETTER:
            return ProcessingResult(ProcessingOutcome.DEAD_LETTER, event.attempt_count)
        handlers = registry.resolve(event.event_type)
        event.status = OutboxStatus.PROCESSING
        event.lease_until = datetime.now(UTC) + timedelta(seconds=settings.worker_lease_seconds)
        for handler in handlers:
            receipt = await session.scalar(
                select(InboxReceipt).where(
                    InboxReceipt.tenant_id == tenant_id,
                    InboxReceipt.event_id == event.id,
                    InboxReceipt.handler_name == handler.name,
                )
            )
            if receipt is None:
                result = await handler.callback(session, event)
                session.add(
                    InboxReceipt(
                        tenant_id=tenant_id,
                        event_id=event.id,
                        handler_name=handler.name,
                        result=result,
                    )
                )
        event.status = OutboxStatus.PUBLISHED
        event.published_at = datetime.now(UTC)
        event.lease_owner = None
        event.lease_until = None
        event.last_error = None
        return ProcessingResult(ProcessingOutcome.PUBLISHED, event.attempt_count)


async def record_failure(
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    error: Exception,
) -> ProcessingResult:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        event = await session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.id == event_id,
            )
            .with_for_update()
        )
        if event is None:
            return ProcessingResult(ProcessingOutcome.NOT_FOUND, 0)
        if event.status is OutboxStatus.PUBLISHED:
            return ProcessingResult(ProcessingOutcome.ALREADY_PUBLISHED, event.attempt_count)
        event.last_error = f"{type(error).__name__}: {error}"[:4000]
        event.lease_owner = None
        event.lease_until = None
        if event.attempt_count >= settings.worker_max_attempts:
            event.status = OutboxStatus.DEAD_LETTER
            event.dead_letter_at = datetime.now(UTC)
            return ProcessingResult(ProcessingOutcome.DEAD_LETTER, event.attempt_count)
        delay = retry_delay_seconds(
            event.attempt_count,
            settings.worker_retry_base_seconds,
            settings.worker_retry_max_seconds,
        )
        event.status = OutboxStatus.RETRY
        event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
        return ProcessingResult(ProcessingOutcome.RETRY_SCHEDULED, event.attempt_count)
