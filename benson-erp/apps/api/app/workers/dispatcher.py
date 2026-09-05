import uuid
from asyncio import to_thread
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.database import SessionFactory
from app.core.tenancy import set_tenant_context
from app.modules.platform.models import Organization, OutboxEvent, OutboxStatus
from app.workers.processor import record_failure

Publisher = Callable[[uuid.UUID, uuid.UUID, uuid.UUID], None]


@dataclass(frozen=True)
class LeasedEvent:
    tenant_id: uuid.UUID
    event_id: uuid.UUID
    correlation_id: uuid.UUID


async def list_tenant_ids() -> list[uuid.UUID]:
    async with SessionFactory() as session:
        return list(await session.scalars(select(Organization.id).order_by(Organization.id)))


async def claim_events(
    tenant_id: uuid.UUID,
    lease_owner: str,
    limit: int,
) -> list[LeasedEvent]:
    now = datetime.now(UTC)
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.dead_letter_at.is_(None),
                    OutboxEvent.next_attempt_at <= now,
                    or_(
                        OutboxEvent.lease_until.is_(None),
                        OutboxEvent.lease_until < now,
                    ),
                )
                .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            event.status = OutboxStatus.LEASED
            event.attempt_count += 1
            event.lease_owner = lease_owner
            event.lease_until = now + timedelta(seconds=settings.worker_lease_seconds)
        return [LeasedEvent(tenant_id, event.id, event.correlation_id) for event in events]


async def mark_dispatched(item: LeasedEvent) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, item.tenant_id)
        event = await session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.tenant_id == item.tenant_id,
                OutboxEvent.id == item.event_id,
            )
            .with_for_update()
        )
        if event is not None and event.status is OutboxStatus.LEASED:
            event.dispatched_at = datetime.now(UTC)


async def dispatch_once(
    publisher: Publisher,
    *,
    tenant_ids: list[uuid.UUID] | None = None,
) -> int:
    lease_owner = f"dispatcher:{uuid.uuid4()}"
    remaining = settings.worker_batch_size
    dispatched = 0
    resolved_tenant_ids = tenant_ids if tenant_ids is not None else await list_tenant_ids()
    for tenant_id in resolved_tenant_ids:
        if remaining == 0:
            break
        items = await claim_events(tenant_id, lease_owner, remaining)
        for item in items:
            try:
                await to_thread(
                    publisher,
                    item.tenant_id,
                    item.event_id,
                    item.correlation_id,
                )
            except Exception as exc:
                await record_failure(item.tenant_id, item.event_id, exc)
                continue
            await mark_dispatched(item)
            dispatched += 1
            remaining -= 1
    return dispatched
