"""‌⁠‍RFI service — business logic for RFI management.

- Event publishing on create/update/delete
- Structured state-change logs (R5: keys = rfi_id / project_id /
  status_from / status_to / actor) so the SIEM ingest pipeline can pivot
  on transitions instead of regex-matching prose log lines
- Retry-on-IntegrityError for RFI-number collisions
  (R5 / BUG-RFI-UNIQ; mirrors the changeorders pattern)
- Respondent identity verification + assigner role gate
  (R5 / BUG-RFI-ROLE; the service is the source of truth, the router
  permission registry is only the coarse first-line filter)
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.rfi.models import RFI
from app.modules.rfi.repository import RFIRepository
from app.modules.rfi.schemas import RFICreate, RFIStatsResponse, RFIUpdate

logger = logging.getLogger(__name__)
_logger_ev = logging.getLogger(__name__ + ".events")


async def _safe_publish(name: str, data: dict, source_module: str = "") -> None:
    try:
        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception:
        _logger_ev.debug("Event publish skipped: %s", name)

_RFI_RESPONSE_DUE_DAYS = 14

# R5 / BUG-RFI-UNIQ: retry budget for ``create_rfi`` when two concurrent
# transactions race on ``max(rfi_number)+1``. Mirrors the changeorders
# code-collision retry loop.
_RFI_CREATE_MAX_RETRIES = 5

# R5 / BUG-RFI-ROLE: roles permitted to (re)assign an RFI. Echoed in the
# permission registry as ``rfi.assign`` (MANAGER+); duplicated at the
# service layer so the FSM check survives any router-level mis-wiring.
_ASSIGNER_ROLES = frozenset({"admin", "manager", "owner"})

# R5 / BUG-RFI-ROLE: roles whose holders may answer an RFI assigned to a
# different user. The intended respondent is the assignee, but
# manager/admin escalations must be able to close out an RFI when the
# assignee is unavailable.
_ESCALATION_ROLES = frozenset({"admin", "manager", "owner"})

# ── Allowed RFI status transitions ────────────────────────────────────────────

_RFI_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"open", "void"},
    "open": {"answered", "closed", "void"},
    "answered": {"closed", "open"},
    "closed": set(),  # terminal
    "void": set(),  # terminal
}


def _add_business_days(start: datetime, days: int) -> str:
    """‌⁠‍Return ISO date string after adding *days* business days to *start*."""
    added = 0
    current = start
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            added += 1
    return current.strftime("%Y-%m-%d")


class RFIService:
    """‌⁠‍Business logic for RFI operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = RFIRepository(session)

    async def create_rfi(
        self,
        data: RFICreate,
        user_id: str | None = None,
    ) -> RFI:
        """Create a new RFI with auto-generated number.

        Ball-in-court is automatically set to ``assigned_to`` when present.
        Response due date defaults to 14 business days from today when the
        status is ``open`` and no explicit due date is provided.

        R5 / BUG-RFI-UNIQ: ``(project_id, rfi_number)`` is now a unique
        constraint. ``next_rfi_number`` reads ``MAX(rfi_number)+1`` outside
        a SERIALIZABLE transaction, so two concurrent calls can pick the
        same suffix. We catch the resulting :class:`IntegrityError`, roll
        back, and retry up to ``_RFI_CREATE_MAX_RETRIES`` times. If every
        retry collides (high contention) we surface HTTP 409 so the
        client retries — never silently writing a duplicate.
        """
        # Auto-set ball_in_court to assigned_to on creation
        ball_in_court = data.ball_in_court
        if ball_in_court is None and data.assigned_to is not None:
            ball_in_court = data.assigned_to

        # BUG-RFI-RAISED-SPOOF: ``raised_by`` is part of the audit log
        # (who filed this RFI) and must always be the authenticated
        # caller. The Pydantic schema still exposes the field — older
        # clients populate it as a convenience and some internal
        # background paths supply it explicitly when no JWT is in
        # scope — but when a real ``user_id`` is in scope it wins
        # unconditionally, so the wire payload cannot impersonate
        # another user. Mirrors the changeorders / variations pattern
        # (created_by is always JWT-derived).
        if user_id:
            try:
                raised_by_val: uuid.UUID | None = uuid.UUID(str(user_id))
            except (ValueError, TypeError):
                raised_by_val = data.raised_by
        else:
            raised_by_val = data.raised_by

        # Auto-calculate response_due_date (14 business days) when status
        # is 'open' and no explicit due date was given.
        response_due_date = data.response_due_date
        if response_due_date is None and data.status == "open":
            response_due_date = _add_business_days(datetime.now(UTC), _RFI_RESPONSE_DUE_DAYS)

        last_exc: Exception | None = None
        for attempt in range(_RFI_CREATE_MAX_RETRIES):
            rfi_number = await self.repo.next_rfi_number(data.project_id)
            rfi = RFI(
                project_id=data.project_id,
                rfi_number=rfi_number,
                subject=data.subject,
                question=data.question,
                raised_by=raised_by_val,
                assigned_to=data.assigned_to,
                status=data.status,
                ball_in_court=ball_in_court,
                cost_impact=data.cost_impact,
                cost_impact_value=data.cost_impact_value,
                schedule_impact=data.schedule_impact,
                schedule_impact_days=data.schedule_impact_days,
                date_required=data.date_required,
                response_due_date=response_due_date,
                linked_drawing_ids=data.linked_drawing_ids,
                change_order_id=data.change_order_id,
                priority=data.priority,
                discipline=data.discipline,
                created_by=user_id,
                metadata_=data.metadata,
            )
            try:
                rfi = await self.repo.create(rfi)
            except IntegrityError as exc:
                # Another transaction picked the same number; roll back
                # and retry with a freshly-bumped suffix.
                last_exc = exc
                await self.session.rollback()
                continue
            logger.info(
                "rfi.created",
                extra={
                    "rfi_id": str(rfi.id),
                    "rfi_number": rfi_number,
                    "project_id": str(data.project_id),
                    "actor": user_id,
                    "attempt": attempt + 1,
                },
            )

            # Publish rfi.assigned event so notification handlers fire
            if data.assigned_to:
                await _safe_publish(
                    "rfi.assigned",
                    {
                        "project_id": str(data.project_id),
                        "rfi_id": str(rfi.id),
                        "rfi_number": rfi_number,
                        "subject": data.subject,
                        "assigned_to": str(data.assigned_to),
                        "assigned_by": user_id or "",
                    },
                    source_module="oe_rfi",
                )

            return rfi

        # Exhausted the retry budget — surface as 409 so the client can
        # back off and retry rather than silently failing.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Could not generate a unique RFI number after "
                f"{_RFI_CREATE_MAX_RETRIES} attempts (concurrent contention)."
            ),
        ) from last_exc

    async def get_rfi(self, rfi_id: uuid.UUID) -> RFI:
        rfi = await self.repo.get_by_id(rfi_id)
        if rfi is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="RFI not found",
            )
        return rfi

    async def list_rfis(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status_filter: str | None = None,
        search: str | None = None,
    ) -> tuple[list[RFI], int]:
        return await self.repo.list_for_project(
            project_id,
            offset=offset,
            limit=limit,
            status=status_filter,
            search=search,
        )

    async def update_rfi(
        self,
        rfi_id: uuid.UUID,
        data: RFIUpdate,
        *,
        actor_id: str | None = None,
        actor_role: str | None = None,
    ) -> RFI:
        """‌⁠‍Patch fields on an RFI, enforcing the FSM + assigner role gate.

        R5 / BUG-RFI-ROLE: only ``admin`` / ``manager`` / ``owner`` may
        change ``assigned_to``. An editor that attempts to reassign gets
        a clean 403 — the rest of the payload is still rejected wholesale
        (atomicity) so the caller never gets a partial update.

        ``actor_role`` is plumbed through from the router so the service
        can enforce the gate without re-reading the JWT. ``None`` means
        the caller is internal (no router-supplied role) — internal
        callers bypass the role check; in practice only background
        subscribers like event handlers reach this path.
        """
        rfi = await self.get_rfi(rfi_id)

        if rfi.status in ("closed", "void"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit an RFI with status '{rfi.status}'",
            )

        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        # R5 / BUG-RFI-ROLE: assigner role gate. ``rfi.update`` (EDITOR)
        # at the router lets an estimator patch body fields, but
        # redirecting ball-in-court is a MANAGER+ action. We refuse the
        # whole request rather than silently dropping ``assigned_to`` so
        # the caller learns what they tried to do.
        if "assigned_to" in fields:
            old_assigned_s = str(rfi.assigned_to) if rfi.assigned_to else None
            requested_s = (
                str(fields["assigned_to"])
                if fields["assigned_to"] is not None
                else None
            )
            if requested_s != old_assigned_s:
                role = (actor_role or "").lower()
                if role and role not in _ASSIGNER_ROLES:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "Only managers or admins may (re)assign an RFI."
                        ),
                    )

        # Validate status transition if status is being changed
        new_status = fields.get("status")
        if new_status is not None and new_status != rfi.status:
            allowed = _RFI_STATUS_TRANSITIONS.get(rfi.status, set())
            if new_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot transition RFI from '{rfi.status}' to '{new_status}'. "
                        f"Allowed transitions: {', '.join(sorted(allowed)) or 'none'}"
                    ),
                )

        # When status transitions to 'open' and no response_due_date is set,
        # auto-calculate it (14 business days from now).
        new_status = fields.get("status")
        if new_status == "open" and not rfi.response_due_date:
            if "response_due_date" not in fields or fields["response_due_date"] is None:
                fields["response_due_date"] = _add_business_days(
                    datetime.now(UTC), _RFI_RESPONSE_DUE_DAYS
                )

        # Auto-update ball_in_court when assigned_to changes
        if "assigned_to" in fields and "ball_in_court" not in fields:
            fields["ball_in_court"] = fields["assigned_to"]

        if not fields:
            return rfi

        # Detect reassignment so we can fire rfi.assigned
        old_assigned = str(rfi.assigned_to) if rfi.assigned_to else None
        new_assigned = fields.get("assigned_to")
        old_status = rfi.status
        # Snapshot attrs before update_fields detaches them from the session.
        project_id_s = str(rfi.project_id)
        rfi_number_s = rfi.rfi_number
        subject_s = rfi.subject

        await self.repo.update_fields(rfi_id, **fields)
        fresh = await self.repo.get_by_id(rfi_id)
        # R5: structured state-change log. SIEM pivots on rfi_id / from /
        # to / actor; the legacy positional log lost the from/to context.
        log_extra: dict[str, Any] = {
            "rfi_id": str(rfi_id),
            "project_id": project_id_s,
            "actor": actor_id,
            "fields": sorted(fields.keys()),
        }
        if new_status is not None and new_status != old_status:
            log_extra["status_from"] = old_status
            log_extra["status_to"] = new_status
            logger.info("rfi.state_change", extra=log_extra)
        else:
            logger.info("rfi.updated", extra=log_extra)

        # Fire rfi.assigned when assigned_to changes to a new user
        if (
            new_assigned is not None
            and str(new_assigned) != old_assigned
        ):
            await _safe_publish(
                "rfi.assigned",
                {
                    "project_id": project_id_s,
                    "rfi_id": str(rfi_id),
                    "rfi_number": rfi_number_s,
                    "subject": subject_s,
                    "assigned_to": str(new_assigned),
                },
                source_module="oe_rfi",
            )

        return fresh or rfi

    async def delete_rfi(
        self, rfi_id: uuid.UUID, *, actor_id: str | None = None
    ) -> None:
        rfi = await self.get_rfi(rfi_id)
        project_id_s = str(rfi.project_id)
        await self.repo.delete(rfi_id)
        logger.info(
            "rfi.deleted",
            extra={
                "rfi_id": str(rfi_id),
                "project_id": project_id_s,
                "actor": actor_id,
            },
        )

    async def respond_to_rfi(
        self,
        rfi_id: uuid.UUID,
        official_response: str,
        responded_by: str,
        *,
        actor_role: str | None = None,
    ) -> RFI:
        """Record an official response to an RFI.

        Ball-in-court automatically flips to ``raised_by`` so the
        originator can review the answer. Publishes ``rfi.responded``
        event so subscribers (notifications, project intelligence) can
        react.

        R5 / BUG-RFI-ROLE: respondent identity verification. An RFI
        assigned to user X may only be answered by:

        1. user X themselves, OR
        2. an ``admin`` / ``manager`` / ``owner`` (escalation chain).

        Unassigned RFIs (``assigned_to IS NULL``) can be answered by any
        caller with ``rfi.respond`` — the router permission already
        covers the coarse gate there. Refusing with 403 (not 404) so the
        assignee knows the RFI exists; the IDOR concern is already
        neutralised by ``verify_project_access`` at the router boundary.
        """
        rfi = await self.get_rfi(rfi_id)
        # BUG-RFI-FSM-RESPOND: ``respond_to_rfi`` used to block only
        # ``closed`` / ``void``, which silently let a ``draft`` (or
        # already-``answered``) RFI leap straight to ``answered`` —
        # bypassing the documented ``draft → open → answered`` flow
        # and overwriting any prior response without a state-change
        # log entry. We now constrain the transition to the single
        # value ``_RFI_STATUS_TRANSITIONS`` permits as a source for
        # ``answered`` (``open``).
        allowed_source_for_answer = {
            src
            for src, targets in _RFI_STATUS_TRANSITIONS.items()
            if "answered" in targets
        }
        if rfi.status not in allowed_source_for_answer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot respond to an RFI with status '{rfi.status}'. "
                    f"Allowed source states: "
                    f"{', '.join(sorted(allowed_source_for_answer)) or 'none'}."
                ),
            )

        # R5 / BUG-RFI-ROLE: identity verification.
        assigned_s = str(rfi.assigned_to) if rfi.assigned_to else None
        if assigned_s and str(responded_by) != assigned_s:
            role = (actor_role or "").lower()
            if role not in _ESCALATION_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Only the assignee or an admin/manager may answer "
                        "this RFI."
                    ),
                )

        # Snapshot attrs before update_fields.
        project_id_s = str(rfi.project_id)
        rfi_number_s = rfi.rfi_number
        subject_s = rfi.subject
        raised_by_s = str(rfi.raised_by) if rfi.raised_by else None
        old_status = rfi.status

        await self.repo.update_fields(
            rfi_id,
            official_response=official_response,
            responded_by=responded_by,
            responded_at=datetime.now(UTC).strftime("%Y-%m-%d"),
            status="answered",
            ball_in_court=str(rfi.raised_by),
        )
        fresh = await self.repo.get_by_id(rfi_id)

        await _safe_publish(
            "rfi.responded",
            {
                "project_id": project_id_s,
                "rfi_id": str(rfi_id),
                "rfi_number": rfi_number_s,
                "subject": subject_s,
                "responded_by": responded_by,
                "raised_by": raised_by_s,
                "ball_in_court": raised_by_s,
            },
            source_module="oe_rfi",
        )

        logger.info(
            "rfi.state_change",
            extra={
                "rfi_id": str(rfi_id),
                "project_id": project_id_s,
                "actor": responded_by,
                "status_from": old_status,
                "status_to": "answered",
                "transition": "respond",
            },
        )
        return fresh or rfi

    async def close_rfi(self, rfi_id: uuid.UUID, *, closed_by: str | None = None) -> RFI:
        """Close an RFI.

        Requires an official response before closing to prevent
        unanswered RFIs from being silently closed. Publishes
        ``rfi.closed`` event.
        """
        rfi = await self.get_rfi(rfi_id)
        if rfi.status == "closed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="RFI is already closed",
            )
        if not rfi.official_response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot close an RFI without an official response",
            )

        project_id_s = str(rfi.project_id)
        rfi_number_s = rfi.rfi_number
        subject_s = rfi.subject
        old_status = rfi.status

        await self.repo.update_fields(rfi_id, status="closed", ball_in_court=None)
        fresh = await self.repo.get_by_id(rfi_id)

        await _safe_publish(
            "rfi.closed",
            {
                "project_id": project_id_s,
                "rfi_id": str(rfi_id),
                "rfi_number": rfi_number_s,
                "subject": subject_s,
                "closed_by": closed_by,
            },
            source_module="oe_rfi",
        )

        logger.info(
            "rfi.state_change",
            extra={
                "rfi_id": str(rfi_id),
                "project_id": project_id_s,
                "actor": closed_by,
                "status_from": old_status,
                "status_to": "closed",
                "transition": "close",
            },
        )
        return fresh or rfi

    async def add_attachment(
        self,
        rfi_id: uuid.UUID,
        attachment_path: str,
    ) -> RFI:
        """‌⁠‍Append a validated attachment path to the RFI.

        R5 / BUG-RFI-ATT: router is responsible for magic-byte validation
        and for picking a server-derived filename. This method only
        mutates the JSON column. We don't log the path payload because
        filenames can carry PII (e.g. ``site_photo_jane_doe.jpg``).
        """
        rfi = await self.get_rfi(rfi_id)
        attachments = list(rfi.attachments or [])
        attachments.append(attachment_path)
        await self.repo.update_fields(rfi_id, attachments=attachments)
        fresh = await self.repo.get_by_id(rfi_id)
        logger.info(
            "rfi.attachment_added",
            extra={
                "rfi_id": str(rfi_id),
                "project_id": str(rfi.project_id),
                "attachment_count": len(attachments),
            },
        )
        return fresh or rfi

    async def get_stats(self, project_id: uuid.UUID) -> RFIStatsResponse:
        """Compute summary statistics for all RFIs in a project.

        Returns total, open, overdue counts, average response time,
        and cost/schedule impact counts.
        """
        from sqlalchemy import select

        now = datetime.now(UTC)
        today_str = now.strftime("%Y-%m-%d")

        # Fetch all RFIs for the project (unfiltered, no pagination)
        base = select(RFI).where(RFI.project_id == project_id)
        result = await self.session.execute(base)
        rfis = list(result.scalars().all())

        total = len(rfis)
        by_status: dict[str, int] = {}
        open_count = 0
        overdue_count = 0
        cost_impact_count = 0
        schedule_impact_count = 0
        response_days: list[float] = []

        for rfi in rfis:
            # Count by status
            by_status[rfi.status] = by_status.get(rfi.status, 0) + 1

            # Open = draft or open
            if rfi.status in ("draft", "open"):
                open_count += 1

            # Overdue = open/draft + past due date
            if rfi.status in ("draft", "open") and rfi.response_due_date:
                try:
                    if rfi.response_due_date < today_str:
                        overdue_count += 1
                except (TypeError, ValueError):
                    pass

            # Impact counts
            if rfi.cost_impact:
                cost_impact_count += 1
            if rfi.schedule_impact:
                schedule_impact_count += 1

            # Average response time (only for answered/closed with responded_at)
            if rfi.status in ("answered", "closed") and rfi.responded_at and rfi.created_at:
                try:
                    resp_date = datetime.fromisoformat(str(rfi.responded_at))
                    if resp_date.tzinfo is None:
                        resp_date = resp_date.replace(tzinfo=UTC)
                    created = rfi.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=UTC)
                    days = max(0.0, (resp_date - created).total_seconds() / 86400)
                    response_days.append(days)
                except (ValueError, TypeError):
                    pass

        avg_days_to_response: float | None = None
        if response_days:
            avg_days_to_response = round(sum(response_days) / len(response_days), 1)

        return RFIStatsResponse(
            total=total,
            by_status=by_status,
            open=open_count,
            overdue=overdue_count,
            avg_days_to_response=avg_days_to_response,
            cost_impact_count=cost_impact_count,
            schedule_impact_count=schedule_impact_count,
        )
