"""‌⁠‍Generic activity-log table and write-through helper.

This is the FSM-aware companion to :mod:`app.core.audit`. While ``audit``
records arbitrary CRUD actions on any entity, ``audit_log`` is structured
specifically around status transitions: every row stores
``(from_status, to_status, action, reason, metadata)`` so dispute
timelines (FIDIC contract records, ISO 9001 traceability, SCL Protocol
contemporary records) can be reproduced byte-for-byte.

Table: ``oe_activity_log``

The existing ``oe_core_audit_log`` table is kept for backwards
compatibility — module services that already use it continue to work,
but new FSM-driven transitions write here as well so the lifecycle of
each entity can be inspected in one place.

Usage::

    from app.core.audit_log import log_activity

    await log_activity(
        session,
        actor_id="user-uuid",
        entity_type="boq",
        entity_id="boq-uuid",
        action="status_changed",
        from_status="draft",
        to_status="final",
        reason="Approved by PM",
        metadata={"approval_doc_id": "..."},
    )
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import JSON, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base

logger = logging.getLogger(__name__)


class ActivityLog(Base):
    """‌⁠‍Append-only audit row recording one entity state change.

    Columns:
        id            — UUID PK (inherited from :class:`Base`).
        tenant_id     — Optional tenant scope. NULL for system events.
        actor_id      — UUID of the user who performed the action (NULL for
                        background jobs).
        entity_type   — Logical entity name: boq / project / invoice / ncr /
                        rfq / submittal / po / gr / …
        entity_id     — UUID of the affected row (string). Stored as text so
                        we can also log events against composite keys later.
        action        — Verb: status_changed / created / updated / deleted /
                        bulk_import / …
        from_status   — Previous status (NULL for create-events).
        to_status     — New status (NULL for delete-events).
        reason        — Free-form note supplied by the user (e.g.
                        "client withdrew approval").
        metadata_     — JSONB with extra context. Stored under column name
                        ``metadata`` but exposed as ``metadata_`` in Python
                        because SQLAlchemy reserves ``metadata`` on the
                        declarative base.
        created_at    — UTC timestamp (inherited from :class:`Base`).
    """

    __tablename__ = "oe_activity_log"
    __table_args__ = (
        Index("ix_activity_log_entity", "entity_type", "entity_id"),
        Index("ix_activity_log_tenant_created", "tenant_id", "created_at"),
        Index("ix_activity_log_actor", "actor_id"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), nullable=True, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return (
            f"<ActivityLog {self.entity_type}:{self.entity_id} "
            f"{self.from_status}->{self.to_status} by {self.actor_id}>"
        )


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def log_activity(
    session: AsyncSession,
    *,
    actor_id: str | uuid.UUID | None,
    entity_type: str,
    entity_id: str | uuid.UUID | None,
    action: str,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | uuid.UUID | None = None,
) -> ActivityLog:
    """‌⁠‍Write a single :class:`ActivityLog` row.

    The session is flushed but NOT committed — the caller's transaction
    boundary owns the commit so audit + business write either both land or
    both roll back. Errors are NOT swallowed here: when the caller wants
    best-effort audit (e.g. from inside a guard), wrap this in try/except.

    Args:
        session: Active async session bound to the same transaction as
            the business write.
        actor_id: UUID of the user. ``None`` for background / system events.
        entity_type: ``boq`` / ``project`` / ``invoice`` / ``ncr`` / ``rfq`` /
            ``submittal`` / ``po`` / ``goods_receipt`` / …
        entity_id: UUID of the affected entity (string or UUID). NULL OK.
        action: Verb describing the event. Use ``status_changed`` for FSM
            transitions and ``created`` / ``updated`` / ``deleted`` for
            ordinary CRUD events.
        from_status: Previous status, or None for new-row events.
        to_status: New status, or None for delete events.
        reason: User-supplied free-form note.
        metadata: Arbitrary JSON payload merged into the row.
        tenant_id: Optional tenant scope (used in multi-tenant deploys).

    Returns:
        The persisted :class:`ActivityLog` instance.
    """
    entry = ActivityLog(
        tenant_id=_coerce_uuid(tenant_id),
        actor_id=_coerce_uuid(actor_id),
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        action=action,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        metadata_=dict(metadata or {}),
    )
    session.add(entry)
    try:
        await session.flush()
    except Exception:  # pragma: no cover — propagated for visibility
        logger.exception(
            "activity_log: flush failed for %s:%s %s",
            entity_type, entity_id, action,
        )
        raise
    logger.debug(
        "activity_log: %s %s %s %s->%s actor=%s",
        action, entity_type, entity_id, from_status, to_status, actor_id,
    )
    return entry


async def get_activity_for_entity(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: str | uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[ActivityLog]:
    """Chronological history (oldest first) for one entity row."""
    eid = str(entity_id)
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.entity_type == entity_type)
        .where(ActivityLog.entity_id == eid)
        .order_by(ActivityLog.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_recent_activity(
    session: AsyncSession,
    *,
    entity_type: str | None = None,
    action: str | None = None,
    actor_id: str | uuid.UUID | None = None,
    limit: int = 50,
) -> list[ActivityLog]:
    """Newest-first query, optionally filtered by entity_type / action / actor."""
    stmt = select(ActivityLog)
    if entity_type is not None:
        stmt = stmt.where(ActivityLog.entity_type == entity_type)
    if action is not None:
        stmt = stmt.where(ActivityLog.action == action)
    if actor_id is not None:
        coerced = _coerce_uuid(actor_id)
        if coerced is not None:
            stmt = stmt.where(ActivityLog.actor_id == coerced)
    stmt = stmt.order_by(ActivityLog.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
