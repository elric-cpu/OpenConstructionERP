import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import settings
from app.core.database import SessionFactory
from app.core.tenancy import set_tenant_context
from app.modules.platform.models import (
    InboxReceipt,
    Organization,
    OutboxEvent,
    OutboxStatus,
)
from app.workers.dispatcher import claim_events, dispatch_once
from app.workers.processor import ProcessingOutcome, process_event
from app.workers.registry import HandlerRegistry
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="PostgreSQL integration tests disabled",
    ),
]


async def test_concurrent_leasing_and_idempotent_processing() -> None:
    tenant_id = uuid.uuid4()
    event_id = await _seed_event(tenant_id, "LeadCreated")
    calls: list[str] = []
    registry = HandlerRegistry()

    async def handler(session, event):
        del session, event
        calls.append("first")
        return {"handled": True}

    async def second_handler(session, event):
        del session, event
        calls.append("second")
        return {"handled": True}

    registry.register("LeadCreated", "test-handler", handler)
    registry.register("LeadCreated", "second-test-handler", second_handler)
    try:
        claims = await _claim_concurrently(tenant_id)
        assert [item.event_id for group in claims for item in group] == [event_id]

        first = await process_event(tenant_id, event_id, registry)
        second = await process_event(tenant_id, event_id, registry)

        assert first.outcome is ProcessingOutcome.PUBLISHED
        assert second.outcome is ProcessingOutcome.ALREADY_PUBLISHED
        assert calls == ["first", "second"]
        event, receipts = await _load_state(tenant_id, event_id)
        assert event.status is OutboxStatus.PUBLISHED
        assert event.attempt_count == 1
        assert event.published_at is not None
        assert receipts == 2
    finally:
        await _clean_tenant(tenant_id)


async def test_failure_retries_then_moves_to_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "worker_max_attempts", 2)
    tenant_id = uuid.uuid4()
    event_id = await _seed_event(tenant_id, "LeadCreated")
    registry = HandlerRegistry()

    async def failing_handler(session, event):
        del session, event
        raise RuntimeError("provider unavailable")

    registry.register("LeadCreated", "failing-handler", failing_handler)
    try:
        assert len(await claim_events(tenant_id, "test-one", 1)) == 1
        first = await process_event(tenant_id, event_id, registry)
        assert first.outcome is ProcessingOutcome.RETRY_SCHEDULED
        await _make_retry_ready(tenant_id, event_id)
        assert len(await claim_events(tenant_id, "test-two", 1)) == 1

        second = await process_event(tenant_id, event_id, registry)

        assert second.outcome is ProcessingOutcome.DEAD_LETTER
        event, receipts = await _load_state(tenant_id, event_id)
        assert event.status is OutboxStatus.DEAD_LETTER
        assert event.attempt_count == 2
        assert event.dead_letter_at is not None
        assert event.last_error == "RuntimeError: provider unavailable"
        assert receipts == 0
    finally:
        await _clean_tenant(tenant_id)


async def test_dispatcher_publishes_tenant_scoped_identity() -> None:
    tenant_id = uuid.uuid4()
    event_id = await _seed_event(tenant_id, "ProjectCreated")
    published: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []
    try:
        count = await dispatch_once(
            lambda tenant, event, correlation: published.append(
                (tenant, event, correlation)
            ),
            tenant_ids=[tenant_id],
        )

        assert count == 1
        assert len(published) == 1
        assert published[0][:2] == (tenant_id, event_id)
        assert isinstance(published[0][2], uuid.UUID)
        event, _ = await _load_state(tenant_id, event_id)
        assert event.status is OutboxStatus.LEASED
        assert event.dispatched_at is not None
        assert event.lease_owner is not None
    finally:
        await _clean_tenant(tenant_id)


async def test_worker_cannot_process_another_tenants_event() -> None:
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    event_id = await _seed_event(tenant_id, "LeadCreated")
    try:
        result = await process_event(other_tenant_id, event_id)

        assert result.outcome is ProcessingOutcome.NOT_FOUND
        event, receipts = await _load_state(tenant_id, event_id)
        assert event.status is OutboxStatus.PENDING
        assert receipts == 0
    finally:
        await _clean_tenant(tenant_id)


async def _claim_concurrently(tenant_id: uuid.UUID):
    return await asyncio.gather(
        claim_events(tenant_id, "dispatcher-one", 1),
        claim_events(tenant_id, "dispatcher-two", 1),
    )


async def _seed_event(tenant_id: uuid.UUID, event_type: str) -> uuid.UUID:
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type="TestAggregate",
        aggregate_id=uuid.uuid4(),
        payload={"test": True},
        correlation_id=uuid.uuid4(),
        idempotency_key=f"test:{uuid.uuid4()}",
    )
    async with SessionFactory() as session, session.begin():
        session.add(
            Organization(
                id=tenant_id,
                name=f"Worker Test {tenant_id}",
                slug=f"worker-test-{tenant_id}",
            )
        )
        await set_tenant_context(session, tenant_id)
        session.add(event)
    return event.id


async def _make_retry_ready(tenant_id: uuid.UUID, event_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        event = await session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.tenant_id == tenant_id, OutboxEvent.id == event_id)
            .with_for_update()
        )
        assert event is not None
        event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)


async def _load_state(
    tenant_id: uuid.UUID, event_id: uuid.UUID
) -> tuple[OutboxEvent, int]:
    async with SessionFactory() as session:
        await set_tenant_context(session, tenant_id)
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.id == event_id,
            )
        )
        receipts = len(
            list(
                await session.scalars(
                    select(InboxReceipt).where(
                        InboxReceipt.tenant_id == tenant_id,
                        InboxReceipt.event_id == event_id,
                    )
                )
            )
        )
        assert event is not None
        return event, receipts


async def _clean_tenant(tenant_id: uuid.UUID) -> None:
    async with SessionFactory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        await session.execute(
            delete(InboxReceipt).where(InboxReceipt.tenant_id == tenant_id)
        )
        await session.execute(
            delete(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id)
        )
        await session.execute(
            delete(Organization).where(Organization.id == tenant_id)
        )
