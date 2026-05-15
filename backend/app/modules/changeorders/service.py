"""‌⁠‍Change Order service — business logic for change order management.

Stateless service layer. Handles:
- Change order CRUD with auto-generated codes
- Item management with cost_delta calculation
- Status transitions (draft -> submitted -> approved/rejected)
- Cost impact recalculation from items
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.changeorders.models import ChangeOrder, ChangeOrderItem
from app.modules.changeorders.repository import ChangeOrderRepository
from app.modules.changeorders.schemas import (
    ChangeOrderCreate,
    ChangeOrderItemCreate,
    ChangeOrderItemUpdate,
    ChangeOrderUpdate,
)

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")


def _dec(value: object) -> Decimal:
    """Coerce an API number (float/int/str) to an exact ``Decimal``.

    Always routes through ``str()`` so a binary float such as ``0.1`` does
    not poison money math with ``0.1000000000000000055…``. Bad input
    degrades to ``Decimal("0")`` rather than raising — the schema layer
    already validates ranges/NaN.
    """
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _round2(value: Decimal) -> Decimal:
    """Round a money ``Decimal`` to 2 dp (HALF_UP) at the persist boundary."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


async def _safe_publish(name: str, data: dict, source_module: str = "") -> None:
    """‌⁠‍Fire-and-forget event publish. Swallows errors so a transient event
    bus outage never breaks the main transaction."""
    try:
        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception:
        logger.debug("Event publish skipped: %s", name)


# Valid status transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["submitted"],
    "submitted": ["approved", "rejected", "draft"],
    "approved": [],
    "rejected": ["draft"],
}


class ChangeOrderService:
    """‌⁠‍Business logic for change order operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChangeOrderRepository(session)

    # ── Create ────────────────────────────────────────────────────────────

    async def create_order(self, data: ChangeOrderCreate) -> ChangeOrder:
        """Create a new change order with auto-generated code.

        BUG-354 race condition: ``count + 1`` is not atomic — two concurrent
        creates could both read ``count=4`` and both emit ``CO-005``. We
        retry on integrity-error (unique-constraint violation) by re-reading
        the current max ordinal from the DB and bumping from there. After
        ``_MAX_RETRIES`` collisions we surface the error rather than looping
        forever.
        """
        from sqlalchemy.exc import IntegrityError

        _MAX_RETRIES = 5

        # BUG-385 follow-up: ``cost_impact`` was silently dropped at create
        # time because it wasn't threaded into the ORM constructor here.
        # The schema now accepts it (added alongside Phase 1); this picks
        # it up so manual-entry COs persist their headline amount. When
        # line items are added later ``add_item`` recomputes the total via
        # ``_recalculate_cost_impact``, so a line-based CO still ends up
        # with the correct sum.
        from decimal import Decimal, InvalidOperation

        try:
            initial_cost_impact = (
                Decimal(str(data.cost_impact)) if data.cost_impact else Decimal("0")
            )
        except (InvalidOperation, ValueError, TypeError):
            initial_cost_impact = Decimal("0")

        # Resolve currency: caller-supplied → project default → "" (honest
        # unknown). Task #217 / the architecture guide forbid a literal "EUR" here — a
        # change order on a BRL/USD/etc. project must inherit that project's
        # currency, never silently become Euro. Resolved once, before the
        # retry loop, so a code-collision retry doesn't re-query the project.
        currency = await self._resolve_currency(data.project_id, data.currency)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            count = await self.repo.count_for_project(data.project_id)
            code = f"CO-{count + 1 + attempt:03d}"

            order = ChangeOrder(
                project_id=data.project_id,
                code=code,
                title=data.title,
                description=data.description,
                reason_category=data.reason_category,
                schedule_impact_days=data.schedule_impact_days,
                currency=currency,
                cost_impact=initial_cost_impact,
                metadata_=data.metadata,
            )
            try:
                order = await self.repo.create(order)
                logger.info(
                    "Change order created: %s for project %s (attempt %d)",
                    code,
                    data.project_id,
                    attempt + 1,
                )
                return order
            except IntegrityError as exc:
                # Another transaction picked the same code. Roll back and
                # retry with a bumped ordinal.
                last_exc = exc
                await self.session.rollback()
                continue

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Could not generate a unique change-order code after "
                f"{_MAX_RETRIES} attempts (concurrent contention). Please retry."
            ),
        ) from last_exc

    async def _resolve_currency(
        self,
        project_id: uuid.UUID,
        requested: str | None,
    ) -> str:
        """Resolve the currency to stamp on a new change order.

        Precedence: explicit caller value → owning project's currency →
        empty string. NEVER returns a literal "EUR": a change order must
        inherit the project's currency so a non-Eurozone project's scope
        changes are not silently mis-stamped as Euro (task #217).
        """
        explicit = (requested or "").strip()
        if explicit:
            return explicit

        from sqlalchemy import select

        from app.modules.projects.models import Project

        try:
            project = (
                await self.session.execute(
                    select(Project).where(Project.id == project_id)
                )
            ).scalar_one_or_none()
        except Exception:
            # No real session (unit-test stub) or transient lookup error —
            # fall back to empty rather than guessing a currency.
            logger.debug("Project currency lookup skipped for %s", project_id)
            return ""
        if project is not None and getattr(project, "currency", None):
            return str(project.currency)
        return ""

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_order(self, order_id: uuid.UUID) -> ChangeOrder:
        """Get change order by ID. Raises 404 if not found."""
        order = await self.repo.get_by_id(order_id)
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Change order not found",
            )
        return order

    async def list_orders(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status_filter: str | None = None,
    ) -> tuple[list[ChangeOrder], int]:
        """List change orders for a project."""
        return await self.repo.list_for_project(
            project_id,
            offset=offset,
            limit=limit,
            status=status_filter,
        )

    async def list_orders_for_owner(
        self,
        owner_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        status_filter: str | None = None,
    ) -> tuple[list[ChangeOrder], int]:
        """List change orders across every project owned by the user."""
        return await self.repo.list_for_owner(
            owner_id,
            offset=offset,
            limit=limit,
            status=status_filter,
        )

    async def get_summary(self, project_id: uuid.UUID) -> dict:
        """Get aggregated stats for a project's change orders."""
        return await self.repo.get_summary(project_id)

    # ── Update ────────────────────────────────────────────────────────────

    async def update_order(
        self,
        order_id: uuid.UUID,
        data: ChangeOrderUpdate,
    ) -> ChangeOrder:
        """Update change order fields. Only draft orders can be edited."""
        order = await self.get_order(order_id)

        if order.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft change orders can be edited",
            )

        fields = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if not fields:
            return order

        await self.repo.update_fields(order_id, **fields)
        await self.session.refresh(order)

        logger.info("Change order updated: %s (fields=%s)", order_id, list(fields.keys()))
        return order

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_order(self, order_id: uuid.UUID) -> None:
        """Delete a change order. Only draft orders can be deleted."""
        order = await self.get_order(order_id)

        if order.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft change orders can be deleted",
            )

        await self.repo.delete(order_id)
        logger.info("Change order deleted: %s", order_id)

    # ── Status transitions ────────────────────────────────────────────────

    async def _assert_not_self_approval(
        self,
        order: "ChangeOrder",
        user_id: str,
        action: str,
    ) -> None:
        """BUG-353: prevent the same user who submitted from approving / rejecting.

        Self-approval is a classic four-eyes-principle violation — in
        construction it means a site manager could both request and sign
        off a scope change without anyone else seeing it. Enforced at
        service layer so router shortcuts don't bypass it.
        """
        if order.submitted_by and str(order.submitted_by) == str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You cannot {action} a change order you submitted yourself "
                    "(four-eyes principle)."
                ),
            )

    async def submit_order(self, order_id: uuid.UUID, user_id: str) -> ChangeOrder:
        """Submit a change order for approval."""
        order = await self.get_order(order_id)
        self._validate_transition(order.status, "submitted")

        now = datetime.now(UTC).isoformat()[:19]
        await self.repo.update_fields(
            order_id,
            status="submitted",
            submitted_by=user_id,
            submitted_at=now,
        )
        await self.session.refresh(order)

        logger.info("Change order submitted: %s by %s", order.code, user_id)
        return order

    async def approve_order(
        self,
        order_id: uuid.UUID,
        user_id: str,
        *,
        boq_id: uuid.UUID | None = None,
    ) -> ChangeOrder:
        """Approve a submitted change order.

        On approval the order's ``cost_impact`` is applied to
        ``project.budget_estimate`` so downstream EVM / reporting reflect the
        new contractual commitment. A ``changeorder.approved`` event is
        published so other modules (budget dashboards, notifications) can
        react without coupling directly to this service.
        """
        from decimal import Decimal, InvalidOperation

        from sqlalchemy import select

        from app.modules.projects.models import Project

        order = await self.get_order(order_id)
        # Idempotent: re-approving an already-approved change order is a
        # no-op (ENH-095). Prevents double budget-writeback if a client
        # retries an approval call after a flaky network round-trip.
        if order.status == "approved":
            return order
        await self._assert_not_self_approval(order, user_id, "approve")
        self._validate_transition(order.status, "approved")

        # Snapshot fields that are safe to use in the event payload later
        # (update_fields calls expire_all). ``project_id_uuid`` keeps the
        # native UUID for downstream SQL (stub tests look up the project
        # by exact UUID match, and Project.id is also typed as UUID).
        project_id_uuid: uuid.UUID = order.project_id
        project_id_s = str(project_id_uuid)
        code_s = order.code
        cost_impact_s = order.cost_impact or "0"
        currency_s = order.currency

        now = datetime.now(UTC).isoformat()[:19]
        await self.repo.update_fields(
            order_id,
            status="approved",
            approved_by=user_id,
            approved_at=now,
        )

        # Writeback: project.budget_estimate += cost_impact. Stored as string
        # to keep Decimal precision regardless of DB backend.
        try:
            delta = Decimal(str(cost_impact_s))
        except (InvalidOperation, ValueError):
            delta = Decimal("0")
        project_updated = False
        if delta != 0:
            # Use the project_id_s snapshot captured before update_fields()
            # called expire_all() — accessing ``order.project_id`` here
            # would trigger a sync-context attribute refresh and raise
            # ``MissingGreenlet`` under async aiosqlite.
            project = (
                await self.session.execute(
                    select(Project).where(Project.id == project_id_uuid)
                )
            ).scalar_one_or_none()
            if project is not None:
                try:
                    current = Decimal(str(project.budget_estimate)) if project.budget_estimate else Decimal("0")
                except (InvalidOperation, ValueError):
                    current = Decimal("0")
                project.budget_estimate = str(current + delta)
                project_updated = True
                await self.session.flush()

        # v2.6.45: Push CO items into the project's primary BOQ as a
        # dedicated section. Construction PMs expect approved scope to
        # appear in the BOQ — previously only project.budget_estimate
        # moved, leaving the BOQ silently out of date.
        # Re-fetch the order so its ``items`` collection is fresh —
        # repo.update_fields() above called session.expire_all() which
        # invalidated the original ORM instance.
        fresh_for_apply = await self.repo.get_by_id(order_id)
        boq_result = await self._apply_to_boq(fresh_for_apply or order, boq_id=boq_id)

        # v2.9.17 Gap B: write a ProjectBudget delta row so EVM BAC reflects
        # the post-CO scope. Wrapped in try/except — never roll back the
        # approval if the budget write fails.
        budget_writeback = await self._write_budget_delta_row(
            order_id=order_id,
            project_id_uuid=project_id_uuid,
            code=code_s,
            cost_impact=delta,
            currency=currency_s,
        )

        await _safe_publish(
            "changeorder.approved",
            {
                "change_order_id": str(order_id),
                "project_id": project_id_s,
                "code": code_s,
                "cost_impact": str(delta),
                "approved_by": user_id,
                "project_budget_updated": project_updated,
                "boq_applied": boq_result.get("applied", False),
                "boq_section_id": boq_result.get("section_id"),
                "boq_positions_added": boq_result.get("positions_added", 0),
                "budget_row_id": budget_writeback.get("budget_id"),
                "budget_row_action": budget_writeback.get("action"),
            },
            source_module="oe_changeorders",
        )

        fresh = await self.repo.get_by_id(order_id)
        logger.info(
            "Change order approved: %s by %s (delta=%s, boq=%s)",
            code_s, user_id, delta, boq_result,
        )
        return fresh or order

    async def _write_budget_delta_row(
        self,
        *,
        order_id: uuid.UUID,
        project_id_uuid: uuid.UUID,
        code: str,
        cost_impact: Decimal,
        currency: str | None,
    ) -> dict:
        """Create or update a ProjectBudget delta row for an approved CO.

        EVM BAC = SUM(revised_budget) across the project's budget rows, so
        approved scope changes need their own row to surface in dashboards.
        Keyed idempotently by ``metadata_->>'change_order_id' == order_id``
        so re-approving (or a second pass on the same CO) updates the
        existing row instead of inserting duplicates.

        Returns ``{"action": "created"|"updated"|"skipped", "budget_id": str|None}``
        — the ``action`` value flows into the ``changeorder.approved`` event
        payload so subscribers can tell what happened. Never raises: a
        budget-write failure must not roll back the approval.
        """
        from sqlalchemy import select

        from app.modules.finance.models import ProjectBudget

        try:
            # Resolve currency: CO-level → project default → "EUR" only as
            # a last-resort literal because ProjectBudget.currency_code is
            # NOT NULL and a missing project here is exceptional.
            currency_code = currency
            if not currency_code:
                from app.modules.projects.models import Project

                project = (
                    await self.session.execute(
                        select(Project).where(Project.id == project_id_uuid)
                    )
                ).scalar_one_or_none()
                if project is not None:
                    currency_code = project.currency
            # Empty when neither CO nor project carries a currency —
            # the budget row stores empty rather than mis-stamping EUR
            # onto a non-Eurozone project.
            currency_code = currency_code or ""

            # Idempotent lookup keyed by metadata.change_order_id.
            existing = (
                await self.session.execute(
                    select(ProjectBudget).where(
                        ProjectBudget.project_id == project_id_uuid
                    )
                )
            ).scalars().all()
            match: ProjectBudget | None = None
            for row in existing:
                md = row.metadata_ if isinstance(row.metadata_, dict) else {}
                if md.get("change_order_id") == str(order_id):
                    match = row
                    break

            category = f"Change Order {code}"
            if match is not None:
                match.revised_budget = cost_impact
                match.currency_code = currency_code
                match.category = category
                # Re-affirm the metadata key in case it was stripped manually.
                md = dict(match.metadata_) if isinstance(match.metadata_, dict) else {}
                md["change_order_id"] = str(order_id)
                md["change_order_code"] = code
                md["origin"] = "change_order"
                match.metadata_ = md
                await self.session.flush()
                return {"action": "updated", "budget_id": str(match.id)}

            budget = ProjectBudget(
                project_id=project_id_uuid,
                wbs_id=str(order_id),
                category=category,
                currency_code=currency_code,
                original_budget=Decimal("0"),
                revised_budget=cost_impact,
                committed=Decimal("0"),
                actual=Decimal("0"),
                forecast_final=Decimal("0"),
                metadata_={
                    "change_order_id": str(order_id),
                    "change_order_code": code,
                    "origin": "change_order",
                },
            )
            self.session.add(budget)
            await self.session.flush()
            return {"action": "created", "budget_id": str(budget.id)}
        except Exception:
            logger.warning(
                "Budget delta-row write failed for change order %s — "
                "approval still committed.",
                code,
                exc_info=True,
            )
            return {"action": "skipped", "budget_id": None}

    async def _apply_to_boq(
        self,
        order: ChangeOrder,
        *,
        boq_id: uuid.UUID | None = None,
    ) -> dict:
        """Push the approved CO's items into the project's first non-locked BOQ.

        Idempotent — if a section with ``metadata.change_order_id == order.id``
        already exists, returns ``already_applied`` and does nothing. Section
        ordinal is ``CO-{code}`` (assumed unique because CO codes are unique
        per project), description ``{code}: {title}``. Each ChangeOrderItem
        becomes a child Position with ``source='manual'`` and metadata link
        back to the CO/CO-item, using the existing schema.

        Returns a dict describing what happened so the event payload can
        surface it to subscribers and the UI:

        - ``applied=True`` + ``section_id`` + ``positions_added`` on success
        - ``applied=False`` + ``reason`` on no-op (no BOQ, all locked, already
          applied, or no items)
        """
        from sqlalchemy import select

        from app.modules.boq.models import BOQ, Position

        # Items must be fetched async — accessing ``order.items`` on an
        # ORM object whose attributes were expired by a prior flush()
        # triggers MissingGreenlet inside async SQLAlchemy. Pull them
        # explicitly so we don't depend on lazy-load state.
        try:
            items = list(
                (
                    await self.session.execute(
                        select(ChangeOrderItem)
                        .where(ChangeOrderItem.change_order_id == order.id)
                        .order_by(ChangeOrderItem.sort_order)
                    )
                ).scalars().all()
            )
        except Exception:
            # Test stubs (SimpleNamespace) don't have a real session.
            # Fall back to whatever the stub exposes.
            items = list(getattr(order, "items", None) or [])
        if not items:
            return {"applied": False, "reason": "no_items"}

        if boq_id is not None:
            boq = (
                await self.session.execute(
                    select(BOQ).where(BOQ.id == boq_id)
                )
            ).scalar_one_or_none()
            if boq is None:
                return {"applied": False, "reason": "boq_not_found"}
            if boq.project_id != order.project_id:
                return {"applied": False, "reason": "boq_project_mismatch"}
            if boq.is_locked:
                return {"applied": False, "reason": "boq_locked"}
        else:
            boq = (
                await self.session.execute(
                    select(BOQ)
                    .where(BOQ.project_id == order.project_id)
                    .where(BOQ.is_locked.is_(False))
                    .order_by(BOQ.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if boq is None:
                logger.info(
                    "Change order %s approved but no unlocked BOQ in project %s "
                    "— BOQ writeback skipped",
                    order.code, order.project_id,
                )
                return {"applied": False, "reason": "no_active_boq"}
            logger.warning(
                "Change order %s applied to BOQ %s by created_at fallback "
                "(no explicit boq_id supplied)",
                order.code, boq.id,
            )

        # Idempotent guard: section keyed by change_order_id in metadata.
        existing_sections = (
            await self.session.execute(
                select(Position)
                .where(Position.boq_id == boq.id)
                .where(Position.unit == "section")
            )
        ).scalars().all()
        for sec in existing_sections:
            md = sec.metadata_ if isinstance(sec.metadata_, dict) else {}
            if md.get("change_order_id") == str(order.id):
                return {
                    "applied": False,
                    "reason": "already_applied",
                    "section_id": str(sec.id),
                }

        # Pick a unique ordinal for the new section. CO codes are unique
        # per project (uq_changeorders_project_code), so ``CO-{code}`` is
        # collision-free across both first-time and re-issued COs.
        section_ordinal = f"CO-{order.code}"
        # Sort_order goes to the end of the BOQ.
        max_order_row = (
            await self.session.execute(
                select(Position.sort_order)
                .where(Position.boq_id == boq.id)
                .order_by(Position.sort_order.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        next_order = (max_order_row or 0) + 1

        section = Position(
            boq_id=boq.id,
            parent_id=None,
            ordinal=section_ordinal,
            description=f"{order.code}: {order.title}",
            unit="section",
            quantity="0",
            unit_rate="0",
            total="0",
            classification={},
            source="manual",
            confidence=None,
            cad_element_ids=[],
            metadata_={
                "change_order_id": str(order.id),
                "change_order_code": order.code,
                "origin": "change_order",
            },
            sort_order=next_order,
        )
        self.session.add(section)
        await self.session.flush()

        positions_added = 0
        item_total = Decimal("0")
        for idx, item in enumerate(items, start=1):
            try:
                qty = Decimal(str(item.new_quantity or "0"))
            except (InvalidOperation, ValueError):
                qty = Decimal("0")
            try:
                rate = Decimal(str(item.new_rate or "0"))
            except (InvalidOperation, ValueError):
                rate = Decimal("0")
            line_total = qty * rate
            item_total += line_total

            position = Position(
                boq_id=boq.id,
                parent_id=section.id,
                ordinal=f"{section_ordinal}.{idx:03d}",
                description=item.description or "(no description)",
                unit=item.unit or "lsum",
                quantity=str(qty),
                unit_rate=str(rate),
                total=str(line_total),
                classification={},
                source="manual",
                confidence=None,
                cad_element_ids=[],
                metadata_={
                    "change_order_id": str(order.id),
                    "change_order_item_id": str(item.id),
                    "change_type": item.change_type,
                    "origin": "change_order",
                },
                sort_order=next_order + idx,
            )
            self.session.add(position)
            positions_added += 1

        # Surface the rolled-up cost on the section row so it's visible in
        # the BOQ tree without forcing the UI to recompute. The UI already
        # treats sections as headers (unit='section'), so the total renders
        # as a subtotal.
        section.total = str(item_total)
        await self.session.flush()

        logger.info(
            "Change order %s applied to BOQ %s: section=%s, %d positions, total=%s",
            order.code, boq.id, section.id, positions_added, item_total,
        )
        return {
            "applied": True,
            "boq_id": str(boq.id),
            "section_id": str(section.id),
            "positions_added": positions_added,
            "section_total": str(item_total),
        }

    async def reject_order(self, order_id: uuid.UUID, user_id: str) -> ChangeOrder:
        """Reject a submitted change order.

        BUG-351: writes to dedicated ``rejected_by`` / ``rejected_at`` fields
        rather than reusing the ``approved_*`` columns. Audit trails and
        dashboards now show "rejected by X" instead of "approved by X"
        when a CO is refused.
        """
        order = await self.get_order(order_id)
        await self._assert_not_self_approval(order, user_id, "reject")
        self._validate_transition(order.status, "rejected")

        now = datetime.now(UTC).isoformat()[:19]
        await self.repo.update_fields(
            order_id,
            status="rejected",
            rejected_by=user_id,
            rejected_at=now,
        )
        fresh = await self.repo.get_by_id(order_id)

        logger.info(
            "Change order rejected: %s by %s",
            (fresh or order).code,
            user_id,
        )
        return fresh or order

    def _validate_transition(self, current: str, target: str) -> None:
        """Validate a status transition."""
        allowed = VALID_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from '{current}' to '{target}'",
            )

    # ── Items ─────────────────────────────────────────────────────────────

    async def add_item(
        self,
        order_id: uuid.UUID,
        data: ChangeOrderItemCreate,
    ) -> ChangeOrderItem:
        """Add an item to a change order and recalculate cost impact."""
        order = await self.get_order(order_id)

        # BUG-352: items are frozen once a CO leaves ``draft``. A submitted
        # CO represents a commitment already under review by the other
        # party, so silently mutating its line items is a contractual
        # integrity hazard. Revert to draft via an explicit transition if
        # changes are needed.
        if order.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Items can only be modified while change order is in 'draft' status",
            )

        # Capture identifying fields BEFORE the recalculation. update_fields
        # expires the session, so accessing `order.code` afterwards would
        # trigger a lazy load and crash with MissingGreenlet in async context.
        order_code = order.code

        # Decimal money math — go through ``str()`` so a float like 0.1
        # doesn't enter the calculation as 0.1000000000000000055…; round
        # only at the persisted boundary (presentation rounds again in the
        # response builder / UI).
        cost_delta = (
            _dec(data.new_quantity) * _dec(data.new_rate)
        ) - (
            _dec(data.original_quantity) * _dec(data.original_rate)
        )

        item = ChangeOrderItem(
            change_order_id=order_id,
            description=data.description,
            change_type=data.change_type,
            original_quantity=str(data.original_quantity),
            new_quantity=str(data.new_quantity),
            original_rate=str(data.original_rate),
            new_rate=str(data.new_rate),
            cost_delta=str(_round2(cost_delta)),
            unit=data.unit,
            sort_order=data.sort_order,
            metadata_=data.metadata,
        )
        item = await self.repo.create_item(item)

        await self._recalculate_cost_impact(order_id)

        # _recalculate_cost_impact expires all session objects, so the freshly
        # created item's attributes are stale — refresh before returning so the
        # router can build the response without lazy-loading.
        await self.session.refresh(item)

        logger.info("Item added to change order %s: %s", order_code, data.description[:40])
        return item

    async def update_item(
        self,
        order_id: uuid.UUID,
        item_id: uuid.UUID,
        data: ChangeOrderItemUpdate,
    ) -> ChangeOrderItem:
        """Update an item and recalculate cost impact."""
        order = await self.get_order(order_id)

        # BUG-352: items are frozen once a CO leaves ``draft``. A submitted
        # CO represents a commitment already under review by the other
        # party, so silently mutating its line items is a contractual
        # integrity hazard. Revert to draft via an explicit transition if
        # changes are needed.
        if order.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Items can only be modified while change order is in 'draft' status",
            )

        item = await self.repo.get_item_by_id(item_id)
        if item is None or item.change_order_id != order_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Change order item not found",
            )

        fields = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        # Recalculate cost_delta if quantities or rates changed. Decimal
        # throughout — mixing the stored string column with an incoming
        # float and rounding once keeps the persisted delta exact.
        orig_qty = _dec(fields.get("original_quantity", item.original_quantity))
        new_qty = _dec(fields.get("new_quantity", item.new_quantity))
        orig_rate = _dec(fields.get("original_rate", item.original_rate))
        new_rate = _dec(fields.get("new_rate", item.new_rate))

        if any(k in fields for k in ("original_quantity", "new_quantity", "original_rate", "new_rate")):
            cost_delta = (new_qty * new_rate) - (orig_qty * orig_rate)
            fields["cost_delta"] = str(_round2(cost_delta))

        # Convert float fields to strings for storage
        for key in ("original_quantity", "new_quantity", "original_rate", "new_rate"):
            if key in fields:
                fields[key] = str(fields[key])

        if fields:
            await self.repo.update_item_fields(item_id, **fields)
            await self._recalculate_cost_impact(order_id)
            await self.session.refresh(item)

        return item

    async def delete_item(self, order_id: uuid.UUID, item_id: uuid.UUID) -> None:
        """Delete an item and recalculate cost impact."""
        order = await self.get_order(order_id)

        # BUG-352: items are frozen once a CO leaves ``draft``. A submitted
        # CO represents a commitment already under review by the other
        # party, so silently mutating its line items is a contractual
        # integrity hazard. Revert to draft via an explicit transition if
        # changes are needed.
        if order.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Items can only be modified while change order is in 'draft' status",
            )

        # Capture the code before recalculation expires the session.
        order_code = order.code

        item = await self.repo.get_item_by_id(item_id)
        if item is None or item.change_order_id != order_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Change order item not found",
            )

        await self.repo.delete_item(item_id)
        await self._recalculate_cost_impact(order_id)

        logger.info("Item deleted from change order %s: %s", order_code, item_id)

    async def _recalculate_cost_impact(self, order_id: uuid.UUID) -> None:
        """Recalculate the total cost impact from all items."""
        items = await self.repo.list_items_for_order(order_id)
        total = sum((_dec(item.cost_delta) for item in items), Decimal("0"))
        await self.repo.update_fields(order_id, cost_impact=str(_round2(total)))
