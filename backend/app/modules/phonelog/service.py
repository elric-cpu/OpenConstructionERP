# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Phone-log service - capture a verbal instruction and read a project's log.

The capture path runs the pure ``phonelog.normalize`` engine over the raw input
so every stored row is canonical (direction, channel, parties, duration,
summary, and the instruction-bearing sentences pulled from the transcript), then
persists it and publishes a ``phone_log.created`` event mirroring the
correspondence module so downstream indexers and timelines can pick it up.

``get_session`` commits after the request completes, so this layer flushes and
never commits - the caller owns the transaction boundary.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.phonelog.models import PhoneLog
from app.modules.phonelog.normalize import PhoneLogInput, normalize
from app.modules.phonelog.schemas import PhoneLogCreate

logger = logging.getLogger(__name__)


async def _safe_publish(name: str, data: dict, source_module: str = "oe_phonelog") -> None:
    """Publish an event, swallowing errors so the capture path never breaks.

    Mirrors correspondence: an event-bus hiccup must not fail the write that the
    user just made - the record is the point, the event is best-effort.
    """
    try:
        from app.core.events import event_bus

        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception as exc:
        logger.debug("Event publish failed for %s: %s", name, exc)


async def create_phone_log(
    session: AsyncSession,
    data: PhoneLogCreate,
    *,
    user_id: str | None = None,
) -> PhoneLog:
    """Normalize a raw capture and persist it as a dispute-ready phone-log row."""
    normalized = normalize(
        PhoneLogInput(
            raw_parties=data.raw_parties,
            direction=data.direction,
            started_at=data.started_at,
            ended_at=data.ended_at,
            duration_seconds=data.duration_seconds,
            transcript=data.transcript,
            summary=data.summary,
            channel=data.channel,
        )
    )

    row = PhoneLog(
        project_id=data.project_id,
        direction=normalized.direction,
        channel=normalized.channel,
        parties=list(normalized.parties),
        occurred_at=data.started_at or None,
        duration_seconds=normalized.duration_seconds,
        # Keep the transcript verbatim - it is the underlying evidence.
        transcript=data.transcript,
        summary=normalized.summary,
        instructions=list(normalized.instructions),
        word_count=normalized.word_count,
        created_by=user_id,
        metadata_=data.metadata,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    # PII discipline: log only structural fields. Transcript / summary / parties
    # can carry personal data and must not reach structured-log sinks.
    logger.info(
        "Phone log captured: %s (%s/%s) for project %s",
        row.id,
        row.direction,
        row.channel,
        data.project_id,
    )
    await _safe_publish(
        "phone_log.created",
        {
            "project_id": str(data.project_id),
            "phone_log_id": str(row.id),
            "direction": row.direction,
            "channel": row.channel,
        },
    )
    return row


async def list_phone_logs(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int = 50,
    direction: str | None = None,
    channel: str | None = None,
) -> tuple[list[PhoneLog], int]:
    """Return a project's phone logs (newest first) and the total match count."""
    stmt = select(PhoneLog).where(PhoneLog.project_id == project_id)
    if direction:
        stmt = stmt.where(PhoneLog.direction == direction)
    if channel:
        stmt = stmt.where(PhoneLog.channel == channel)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await session.execute(stmt.order_by(PhoneLog.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    )
    return list(rows), int(total)


async def get_phone_log(session: AsyncSession, phone_log_id: uuid.UUID) -> PhoneLog | None:
    """Fetch a single phone log by id, or None when it does not exist."""
    return (await session.execute(select(PhoneLog).where(PhoneLog.id == phone_log_id))).scalar_one_or_none()
