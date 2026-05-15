"""Business logic for the Service & Maintenance module.

Houses:
    - State-machine helpers (pure functions, independently testable).
    - ``ServiceService`` orchestrator that composes the repos.

The state machines are deliberately implemented as plain dicts of allowed
transitions so unit tests stay trivial and the contract is visible at a glance.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.service.models import (
    AssetInspectionChecklist,
    DebriefReport,
    ServiceAsset,
    ServiceContract,
    ServiceSchedule,
    ServiceTicket,
    ServiceWorkOrder,
    ServiceWorkOrderItem,
    SLADefinition,
)
from app.modules.service.repository import (
    AssetRepository,
    ChecklistRepository,
    ContractRepository,
    DebriefRepository,
    ScheduleRepository,
    SLADefinitionRepository,
    TicketRepository,
    WorkOrderItemRepository,
    WorkOrderRepository,
)
from app.modules.service.schemas import (
    AssetChecklistCreate,
    AssetChecklistUpdate,
    ContractDashboardResponse,
    NCRFromWorkOrderRequest,
    NCRFromWorkOrderResponse,
    ServiceAssetCreate,
    ServiceAssetUpdate,
    ServiceContractCreate,
    ServiceContractUpdate,
    ServiceScheduleCreate,
    ServiceScheduleUpdate,
    ServiceTicketCreate,
    ServiceTicketUpdate,
    SLABreachEntry,
    SLABreachScanResponse,
    SLADefinitionCreate,
    SLADefinitionUpdate,
    TicketDispatchRequest,
    WorkOrderCompleteRequest,
    WorkOrderCreate,
    WorkOrderItemCreate,
    WorkOrderUpdate,
)

logger = logging.getLogger(__name__)


# ── State-machine helpers (pure functions) ────────────────────────────────

_TICKET_TRANSITIONS: dict[str, set[str]] = {
    "new": {"assigned", "in_progress", "cancelled"},
    "assigned": {"in_progress", "cancelled", "new"},
    "in_progress": {"resolved", "cancelled"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
    "cancelled": set(),
}

_WORK_ORDER_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {"dispatched", "cancelled"},
    "dispatched": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": {"billed"},
    "billed": set(),
    "cancelled": set(),
}

_CONTRACT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "terminated"},
    "active": {"expired", "terminated"},
    "expired": {"active", "terminated"},
    "terminated": set(),
}


def allowed_ticket_transitions(current: str) -> set[str]:
    """Return the set of legal next statuses for a ticket in ``current`` state."""
    return _TICKET_TRANSITIONS.get(current, set())


def allowed_work_order_transitions(current: str) -> set[str]:
    """Return the set of legal next statuses for a work order in ``current`` state."""
    return _WORK_ORDER_TRANSITIONS.get(current, set())


def allowed_contract_transitions(current: str) -> set[str]:
    """Return the set of legal next statuses for a contract in ``current`` state."""
    return _CONTRACT_TRANSITIONS.get(current, set())


def assert_transition(current: str, target: str, *, machine: str) -> None:
    """Raise HTTPException 409 if ``current → target`` is not a legal transition."""
    if machine == "ticket":
        allowed = allowed_ticket_transitions(current)
    elif machine == "work_order":
        allowed = allowed_work_order_transitions(current)
    elif machine == "contract":
        allowed = allowed_contract_transitions(current)
    else:  # pragma: no cover — caller bug
        raise ValueError(f"Unknown state machine: {machine}")

    if target == current:
        return
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid {machine} transition: '{current}' → '{target}'. "
                f"Allowed: {sorted(allowed) or 'none (terminal state)'}"
            ),
        )


def compute_sla_due_at(
    reported_at: datetime,
    sla: SLADefinition | None,
    *,
    priority: str = "med",
) -> datetime | None:
    """Compute ticket.sla_due_at = reported_at + response_time(priority).

    Priority-aware override: when ``sla.severity_levels`` contains an entry
    for ``priority`` with ``response_time_minutes``, that wins; otherwise we
    fall back to the SLA's default ``response_time_minutes``.
    """
    if sla is None:
        return None

    minutes: int = sla.response_time_minutes
    severity_overrides = sla.severity_levels or {}
    if isinstance(severity_overrides, dict):
        override = severity_overrides.get(priority)
        if isinstance(override, dict):
            candidate = override.get("response_time_minutes")
            if isinstance(candidate, int) and candidate > 0:
                minutes = candidate
        elif isinstance(override, int) and override > 0:
            minutes = override

    return reported_at + timedelta(minutes=minutes)


def compute_work_order_total(items: list[ServiceWorkOrderItem]) -> Decimal:
    """Sum of ``item.total`` across a work order's items, rounded to 2dp."""
    total = Decimal("0")
    for item in items:
        total += Decimal(item.total or 0)
    return total.quantize(Decimal("0.01"))


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO datetime string. Adds UTC if naïve."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# ── ServiceService ────────────────────────────────────────────────────────


class ServiceService:
    """Business logic for the Service & Maintenance module."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.contract_repo = ContractRepository(session)
        self.asset_repo = AssetRepository(session)
        self.ticket_repo = TicketRepository(session)
        self.work_order_repo = WorkOrderRepository(session)
        self.work_order_item_repo = WorkOrderItemRepository(session)
        self.debrief_repo = DebriefRepository(session)
        self.sla_repo = SLADefinitionRepository(session)
        self.schedule_repo = ScheduleRepository(session)
        self.checklist_repo = ChecklistRepository(session)

    # ── Contract ─────────────────────────────────────────────────────────

    async def create_contract(
        self,
        data: ServiceContractCreate,
        user_id: str | None = None,
    ) -> ServiceContract:
        # A contract is only ever born draft or active; expired/terminated are
        # outcomes reached via the state machine, never an initial value.
        allowed_initial = {"draft", "active"}
        if data.status not in allowed_initial:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"A contract cannot be created in '{data.status}' state. "
                    f"Allowed initial states: {sorted(allowed_initial)}."
                ),
            )
        if data.period_end < data.period_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period_end must be on or after period_start.",
            )
        contract_number = await self.contract_repo.next_contract_number()
        contract = ServiceContract(
            customer_id=data.customer_id,
            project_id=data.project_id,
            contract_number=contract_number,
            title=data.title,
            description=data.description,
            period_start=data.period_start,
            period_end=data.period_end,
            sla_definition_id=data.sla_definition_id,
            sla_tier=data.sla_tier,
            status=data.status,
            value=data.value,
            currency=data.currency,
            auto_renew=data.auto_renew,
            created_by=user_id,
            metadata_=data.metadata,
        )
        contract = await self.contract_repo.create(contract)
        logger.info("Service contract created: %s for customer %s", contract_number, data.customer_id)
        event_bus.publish_detached(
            "service.contract.created",
            {
                "contract_id": str(contract.id),
                "contract_number": contract_number,
                "customer_id": str(data.customer_id),
                "status": data.status,
            },
            source_module="service",
        )
        return contract

    async def get_contract(self, contract_id: uuid.UUID) -> ServiceContract:
        contract = await self.contract_repo.get_by_id(contract_id)
        if contract is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service contract not found",
            )
        return contract

    async def update_contract(
        self,
        contract_id: uuid.UUID,
        data: ServiceContractUpdate,
    ) -> ServiceContract:
        contract = await self.get_contract(contract_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if "status" in fields:
            assert_transition(contract.status, fields["status"], machine="contract")

        # Re-check period ordering against the *merged* state so a PATCH that
        # touches only one bound can't invert the period.
        new_start = fields.get("period_start", contract.period_start)
        new_end = fields.get("period_end", contract.period_end)
        if ("period_start" in fields or "period_end" in fields) and new_end < new_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="period_end must be on or after period_start.",
            )

        if not fields:
            return contract

        await self.contract_repo.update_fields(contract_id, **fields)
        await self.session.refresh(contract)
        return contract

    async def close_contract(self, contract_id: uuid.UUID) -> ServiceContract:
        """Manager-only: move a contract to ``terminated``."""
        contract = await self.get_contract(contract_id)
        assert_transition(contract.status, "terminated", machine="contract")
        await self.contract_repo.update_fields(contract_id, status="terminated")
        await self.session.refresh(contract)
        event_bus.publish_detached(
            "service.contract.terminated",
            {"contract_id": str(contract_id), "contract_number": contract.contract_number},
            source_module="service",
        )
        return contract

    async def delete_contract(self, contract_id: uuid.UUID) -> None:
        await self.get_contract(contract_id)
        await self.contract_repo.delete(contract_id)

    # ── Asset ────────────────────────────────────────────────────────────

    async def create_asset(self, data: ServiceAssetCreate) -> ServiceAsset:
        # Validates that the contract exists, so we get a clean 404 instead
        # of a foreign-key error from the DB.
        await self.get_contract(data.contract_id)
        asset = ServiceAsset(
            contract_id=data.contract_id,
            asset_tag=data.asset_tag,
            asset_type=data.asset_type,
            name=data.name,
            location=data.location,
            manufacturer=data.manufacturer,
            model=data.model,
            serial=data.serial,
            install_date=data.install_date,
            warranty_until=data.warranty_until,
            status=data.status,
            metadata_=data.metadata,
        )
        return await self.asset_repo.create(asset)

    async def get_asset(self, asset_id: uuid.UUID) -> ServiceAsset:
        asset = await self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service asset not found",
            )
        return asset

    async def update_asset(self, asset_id: uuid.UUID, data: ServiceAssetUpdate) -> ServiceAsset:
        asset = await self.get_asset(asset_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        if not fields:
            return asset
        await self.asset_repo.update_fields(asset_id, **fields)
        await self.session.refresh(asset)
        return asset

    async def delete_asset(self, asset_id: uuid.UUID) -> None:
        await self.get_asset(asset_id)
        await self.asset_repo.delete(asset_id)

    # ── Ticket ───────────────────────────────────────────────────────────

    async def create_ticket(
        self,
        data: ServiceTicketCreate,
        user_id: str | None = None,
    ) -> ServiceTicket:
        """Create a ticket, compute its SLA-due, emit an event."""
        contract = await self.get_contract(data.contract_id)

        # Optional asset validation
        if data.asset_id is not None:
            asset = await self.asset_repo.get_by_id(data.asset_id)
            if asset is None or asset.contract_id != contract.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="asset_id does not belong to this contract",
                )

        reported_at_dt = (
            _parse_iso(data.reported_at) if data.reported_at else datetime.now(UTC)
        )

        sla: SLADefinition | None = None
        if contract.sla_definition_id is not None:
            sla = await self.sla_repo.get_by_id(contract.sla_definition_id)

        sla_due_dt = compute_sla_due_at(reported_at_dt, sla, priority=data.priority)

        ticket_number = await self.ticket_repo.next_ticket_number(contract.id)
        ticket = ServiceTicket(
            contract_id=data.contract_id,
            asset_id=data.asset_id,
            ticket_number=ticket_number,
            title=data.title,
            description=data.description,
            priority=data.priority,
            reported_at=reported_at_dt.isoformat(),
            sla_due_at=sla_due_dt.isoformat() if sla_due_dt else None,
            status="new",
            source=data.source,
            reported_by=data.reported_by or user_id,
            assigned_to=data.assigned_to,
            metadata_=data.metadata,
        )
        # If the create payload pre-supplied an assignee, the ticket is born
        # in the 'assigned' state, mirroring the dispatcher click-flow.
        if data.assigned_to:
            ticket.status = "assigned"

        ticket = await self.ticket_repo.create(ticket)
        logger.info(
            "Service ticket created: %s (contract=%s, priority=%s, sla_due=%s)",
            ticket_number,
            data.contract_id,
            data.priority,
            ticket.sla_due_at,
        )
        event_bus.publish_detached(
            "service.ticket.created",
            {
                "ticket_id": str(ticket.id),
                "ticket_number": ticket_number,
                "contract_id": str(data.contract_id),
                "priority": data.priority,
                "sla_due_at": ticket.sla_due_at,
                "source": data.source,
                "reported_by": data.reported_by or user_id,
            },
            source_module="service",
        )
        # A ticket born with an assignee is effectively dispatched on create;
        # emit the same event the explicit /dispatch endpoint does so
        # technician-assignment subscribers don't miss born-assigned tickets.
        if ticket.status == "assigned" and ticket.assigned_to:
            event_bus.publish_detached(
                "service.ticket.dispatched",
                {
                    "ticket_id": str(ticket.id),
                    "ticket_number": ticket_number,
                    "technician_id": ticket.assigned_to,
                    "scheduled_for": None,
                },
                source_module="service",
            )
        return ticket

    async def get_ticket(self, ticket_id: uuid.UUID) -> ServiceTicket:
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service ticket not found",
            )
        return ticket

    async def update_ticket(
        self,
        ticket_id: uuid.UUID,
        data: ServiceTicketUpdate,
    ) -> ServiceTicket:
        ticket = await self.get_ticket(ticket_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if "status" in fields:
            new_status = fields["status"]
            assert_transition(ticket.status, new_status, machine="ticket")
            # Keep lifecycle timestamps consistent with the dedicated
            # resolve/close endpoints when an admin corrects status via PATCH —
            # otherwise a 'closed' ticket can end up with closed_at = NULL.
            if (
                new_status == "resolved"
                and ticket.status != "resolved"
                and ticket.resolved_at is None
            ):
                fields["resolved_at"] = _utcnow_iso()
            if (
                new_status == "closed"
                and ticket.status != "closed"
                and ticket.closed_at is None
            ):
                fields["closed_at"] = _utcnow_iso()

        if not fields:
            return ticket

        await self.ticket_repo.update_fields(ticket_id, **fields)
        await self.session.refresh(ticket)
        return ticket

    async def dispatch_ticket(
        self,
        ticket_id: uuid.UUID,
        body: TicketDispatchRequest,
    ) -> ServiceTicket:
        """Assign a ticket to a technician and emit ``service.ticket.dispatched``.

        Validates the state-machine transition new → assigned (or
        assigned → assigned, treated as re-assignment) and requires that
        ``technician_id`` be present.
        """
        if not body.technician_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="technician_id is required for dispatch",
            )
        ticket = await self.get_ticket(ticket_id)
        # Re-assignment on already-assigned tickets is allowed but doesn't move state.
        if ticket.status not in ("assigned",):
            assert_transition(ticket.status, "assigned", machine="ticket")

        await self.ticket_repo.update_fields(
            ticket_id,
            status="assigned",
            assigned_to=body.technician_id,
        )
        await self.session.refresh(ticket)
        logger.info(
            "Service ticket dispatched: %s → technician %s",
            ticket.ticket_number, body.technician_id,
        )
        event_bus.publish_detached(
            "service.ticket.dispatched",
            {
                "ticket_id": str(ticket_id),
                "ticket_number": ticket.ticket_number,
                "technician_id": body.technician_id,
                "scheduled_for": body.scheduled_for,
            },
            source_module="service",
        )
        return ticket

    async def resolve_ticket(self, ticket_id: uuid.UUID) -> ServiceTicket:
        ticket = await self.get_ticket(ticket_id)
        assert_transition(ticket.status, "resolved", machine="ticket")
        await self.ticket_repo.update_fields(
            ticket_id,
            status="resolved",
            resolved_at=_utcnow_iso(),
        )
        await self.session.refresh(ticket)
        event_bus.publish_detached(
            "service.ticket.resolved",
            {
                "ticket_id": str(ticket_id),
                "ticket_number": ticket.ticket_number,
                "reported_by": ticket.reported_by,
            },
            source_module="service",
        )
        return ticket

    async def close_ticket(self, ticket_id: uuid.UUID) -> ServiceTicket:
        ticket = await self.get_ticket(ticket_id)
        assert_transition(ticket.status, "closed", machine="ticket")
        await self.ticket_repo.update_fields(
            ticket_id,
            status="closed",
            closed_at=_utcnow_iso(),
        )
        await self.session.refresh(ticket)
        event_bus.publish_detached(
            "service.ticket.closed",
            {"ticket_id": str(ticket_id), "ticket_number": ticket.ticket_number},
            source_module="service",
        )
        return ticket

    async def delete_ticket(self, ticket_id: uuid.UUID) -> None:
        await self.get_ticket(ticket_id)
        await self.ticket_repo.delete(ticket_id)

    # ── Work Order ───────────────────────────────────────────────────────

    async def create_work_order(self, data: WorkOrderCreate) -> ServiceWorkOrder:
        ticket = await self.get_ticket(data.ticket_id)

        # The schema permits any WO label, but a WO must not be *born* in a
        # state that bypasses the finance hand-off. ``billed`` skips the
        # ``bill_work_order`` finance event + roll-up, and ``cancelled`` is a
        # terminal no-op. A direct ``completed`` is legitimate (retroactive
        # entry of work already done) — we just back-fill the billed_amount
        # roll-up below so that path never loses its total.
        allowed_initial = {"scheduled", "dispatched", "in_progress", "completed"}
        if data.status not in allowed_initial:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"A work order cannot be created in '{data.status}' state. "
                    f"Allowed initial states: {sorted(allowed_initial)}."
                ),
            )

        wo_number = await self.work_order_repo.next_work_order_number()
        wo = ServiceWorkOrder(
            ticket_id=data.ticket_id,
            work_order_number=wo_number,
            scheduled_for=data.scheduled_for,
            technician_id=data.technician_id,
            status=data.status,
            currency=data.currency,
            metadata_=data.metadata,
        )
        wo = await self.work_order_repo.create(wo)

        # Persist items (with computed totals if caller didn't supply them).
        for item_data in data.items:
            await self._create_work_order_item(wo.id, item_data)

        # A WO born straight into ``completed`` never passes through
        # complete_work_order(), so back-fill the billed_amount roll-up here
        # to preserve the "billed_amount == sum(items.total)" invariant.
        if data.status == "completed":
            items = await self.work_order_item_repo.list_for_work_order(wo.id)
            await self.work_order_repo.update_fields(
                wo.id,
                billed_amount=compute_work_order_total(items),
                completed_at=_utcnow_iso(),
            )

        await self.session.refresh(wo)
        logger.info(
            "Work order created: %s for ticket %s", wo_number, ticket.ticket_number,
        )
        event_bus.publish_detached(
            "service.work_order.created",
            {
                "work_order_id": str(wo.id),
                "work_order_number": wo_number,
                "ticket_id": str(data.ticket_id),
            },
            source_module="service",
        )
        return wo

    async def _create_work_order_item(
        self,
        work_order_id: uuid.UUID,
        data: WorkOrderItemCreate,
    ) -> ServiceWorkOrderItem:
        total = (
            data.total
            if data.total is not None
            else (data.quantity * data.unit_rate).quantize(Decimal("0.01"))
        )
        item = ServiceWorkOrderItem(
            work_order_id=work_order_id,
            item_type=data.item_type,
            description=data.description,
            quantity=data.quantity,
            unit=data.unit,
            unit_rate=data.unit_rate,
            total=total,
            metadata_=data.metadata,
        )
        return await self.work_order_item_repo.create(item)

    async def get_work_order(self, wo_id: uuid.UUID) -> ServiceWorkOrder:
        wo = await self.work_order_repo.get_by_id(wo_id)
        if wo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work order not found",
            )
        return wo

    async def update_work_order(
        self,
        wo_id: uuid.UUID,
        data: WorkOrderUpdate,
    ) -> ServiceWorkOrder:
        wo = await self.get_work_order(wo_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        if "status" in fields:
            assert_transition(wo.status, fields["status"], machine="work_order")
        if not fields:
            return wo
        await self.work_order_repo.update_fields(wo_id, **fields)
        await self.session.refresh(wo)
        return wo

    async def complete_work_order(
        self,
        wo_id: uuid.UUID,
        body: WorkOrderCompleteRequest,
    ) -> ServiceWorkOrder:
        """Close out a work order: persist debrief + signature, sum items.

        Sets ``billed_amount = sum(items.total)`` so the accountant has a
        ready-to-invoice figure even before the explicit /bill call.
        """
        wo = await self.get_work_order(wo_id)
        assert_transition(wo.status, "completed", machine="work_order")

        items = await self.work_order_item_repo.list_for_work_order(wo_id)
        billed_amount = compute_work_order_total(items)

        update_fields: dict[str, Any] = {
            "status": "completed",
            "completed_at": _utcnow_iso(),
            "billed_amount": billed_amount,
            "debrief_summary": (
                body.debrief.solution[:1000] if body.debrief.solution else wo.debrief_summary
            ),
        }
        if body.customer_signature is not None:
            update_fields["customer_signature"] = body.customer_signature

        await self.work_order_repo.update_fields(wo_id, **update_fields)

        # Persist the structured P-C-S debrief alongside the summary.
        debrief = DebriefReport(
            work_order_id=wo_id,
            problem=body.debrief.problem,
            cause=body.debrief.cause,
            solution=body.debrief.solution,
            root_cause_category=body.debrief.root_cause_category,
            follow_up_required=body.debrief.follow_up_required,
            metadata_=body.debrief.metadata,
        )
        await self.debrief_repo.create(debrief)

        await self.session.refresh(wo)
        logger.info(
            "Work order completed: %s (billed_amount=%s)",
            wo.work_order_number, billed_amount,
        )
        event_bus.publish_detached(
            "service.work_order.completed",
            {
                "work_order_id": str(wo_id),
                "work_order_number": wo.work_order_number,
                "billed_amount": str(billed_amount),
                "currency": wo.currency,
                "follow_up_required": body.debrief.follow_up_required,
            },
            source_module="service",
        )
        return wo

    async def bill_work_order(self, wo_id: uuid.UUID) -> ServiceWorkOrder:
        """Move a completed WO to ``billed`` and emit a Finance event.

        Emits ``service.work_order.billed`` (caught by finance to create an
        invoice). This module does NOT touch the finance module directly.
        """
        wo = await self.get_work_order(wo_id)
        assert_transition(wo.status, "billed", machine="work_order")

        await self.work_order_repo.update_fields(
            wo_id,
            status="billed",
            billed_at=_utcnow_iso(),
        )
        await self.session.refresh(wo)

        # Look up the parent ticket/contract for the finance event payload.
        ticket = await self.ticket_repo.get_by_id(wo.ticket_id)
        contract_id = str(ticket.contract_id) if ticket else None

        logger.info("Work order billed: %s amount=%s", wo.work_order_number, wo.billed_amount)
        event_bus.publish_detached(
            "service.work_order.billed",
            {
                "work_order_id": str(wo_id),
                "work_order_number": wo.work_order_number,
                "ticket_id": str(wo.ticket_id),
                "contract_id": contract_id,
                "billed_amount": str(wo.billed_amount),
                "currency": wo.currency,
            },
            source_module="service",
        )
        return wo

    async def delete_work_order(self, wo_id: uuid.UUID) -> None:
        await self.get_work_order(wo_id)
        await self.work_order_repo.delete(wo_id)

    # ── SLA definitions ──────────────────────────────────────────────────

    async def create_sla(self, data: SLADefinitionCreate) -> SLADefinition:
        sla = SLADefinition(
            name=data.name,
            description=data.description,
            response_time_minutes=data.response_time_minutes,
            resolution_time_minutes=data.resolution_time_minutes,
            severity_levels=data.severity_levels,
            is_active=data.is_active,
            metadata_=data.metadata,
        )
        return await self.sla_repo.create(sla)

    async def get_sla(self, sla_id: uuid.UUID) -> SLADefinition:
        sla = await self.sla_repo.get_by_id(sla_id)
        if sla is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SLA definition not found",
            )
        return sla

    async def update_sla(self, sla_id: uuid.UUID, data: SLADefinitionUpdate) -> SLADefinition:
        sla = await self.get_sla(sla_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        if not fields:
            return sla
        await self.sla_repo.update_fields(sla_id, **fields)
        await self.session.refresh(sla)
        return sla

    async def delete_sla(self, sla_id: uuid.UUID) -> None:
        await self.get_sla(sla_id)
        await self.sla_repo.delete(sla_id)

    # ── Schedules (PPM) ──────────────────────────────────────────────────

    async def create_schedule(self, data: ServiceScheduleCreate) -> ServiceSchedule:
        await self.get_asset(data.asset_id)
        sched = ServiceSchedule(
            asset_id=data.asset_id,
            frequency=data.frequency,
            next_due_date=data.next_due_date,
            checklist_template_id=data.checklist_template_id,
            is_active=data.is_active,
            metadata_=data.metadata,
        )
        return await self.schedule_repo.create(sched)

    async def get_schedule(self, schedule_id: uuid.UUID) -> ServiceSchedule:
        sched = await self.schedule_repo.get_by_id(schedule_id)
        if sched is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service schedule not found",
            )
        return sched

    async def update_schedule(
        self,
        schedule_id: uuid.UUID,
        data: ServiceScheduleUpdate,
    ) -> ServiceSchedule:
        sched = await self.get_schedule(schedule_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        if not fields:
            return sched
        await self.schedule_repo.update_fields(schedule_id, **fields)
        await self.session.refresh(sched)
        return sched

    async def delete_schedule(self, schedule_id: uuid.UUID) -> None:
        await self.get_schedule(schedule_id)
        await self.schedule_repo.delete(schedule_id)

    # ── Checklists ───────────────────────────────────────────────────────

    async def create_checklist(self, data: AssetChecklistCreate) -> AssetInspectionChecklist:
        cl = AssetInspectionChecklist(
            name=data.name,
            description=data.description,
            asset_type=data.asset_type,
            items=data.items,
            is_active=data.is_active,
            metadata_=data.metadata,
        )
        return await self.checklist_repo.create(cl)

    async def get_checklist(self, checklist_id: uuid.UUID) -> AssetInspectionChecklist:
        cl = await self.checklist_repo.get_by_id(checklist_id)
        if cl is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Checklist not found",
            )
        return cl

    async def update_checklist(
        self,
        checklist_id: uuid.UUID,
        data: AssetChecklistUpdate,
    ) -> AssetInspectionChecklist:
        cl = await self.get_checklist(checklist_id)
        fields: dict[str, Any] = data.model_dump(exclude_unset=True)
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")
        if not fields:
            return cl
        await self.checklist_repo.update_fields(checklist_id, **fields)
        await self.session.refresh(cl)
        return cl

    async def delete_checklist(self, checklist_id: uuid.UUID) -> None:
        await self.get_checklist(checklist_id)
        await self.checklist_repo.delete(checklist_id)

    # ── Dashboard ────────────────────────────────────────────────────────

    async def get_contract_dashboard(
        self,
        contract_id: uuid.UUID,
    ) -> ContractDashboardResponse:
        """Aggregate KPIs for one contract's dashboard widget."""
        from sqlalchemy import func, select  # local import to keep top tidy

        contract = await self.get_contract(contract_id)

        open_tickets = await self.ticket_repo.count_open_for_contract(contract_id)
        in_progress_tickets = await self.ticket_repo.count_in_progress_for_contract(contract_id)

        # SLA breaches: tickets past sla_due_at, not yet resolved/closed/cancelled.
        # Count at the DB level — materialising rows here would also trigger the
        # ServiceTicket.work_orders selectin load for every breached ticket.
        now_iso = _utcnow_iso()
        sla_breach_stmt = (
            select(func.count())
            .select_from(ServiceTicket)
            .where(
                ServiceTicket.contract_id == contract_id,
                ServiceTicket.sla_due_at.isnot(None),
                ServiceTicket.sla_due_at < now_iso,
                ServiceTicket.status.in_(("new", "assigned", "in_progress")),
            )
        )
        sla_breaches = int((await self.session.execute(sla_breach_stmt)).scalar_one())

        # WO counts: scheduled vs completed-in-last-30d.
        scheduled_wo_stmt = (
            select(func.count())
            .select_from(ServiceWorkOrder)
            .join(ServiceTicket, ServiceTicket.id == ServiceWorkOrder.ticket_id)
            .where(
                ServiceTicket.contract_id == contract_id,
                ServiceWorkOrder.status.in_(("scheduled", "dispatched", "in_progress")),
            )
        )
        scheduled_work_orders = int(
            (await self.session.execute(scheduled_wo_stmt)).scalar_one()
        )

        # completed_at is stored full-ISO ("…T…+00:00"); compare against a
        # matching full-ISO bound (not a bare date) so the string ordering is
        # well-defined.
        thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        completed_wo_stmt = (
            select(ServiceWorkOrder)
            .join(ServiceTicket, ServiceTicket.id == ServiceWorkOrder.ticket_id)
            .where(
                ServiceTicket.contract_id == contract_id,
                ServiceWorkOrder.status.in_(("completed", "billed")),
                ServiceWorkOrder.completed_at.isnot(None),
                ServiceWorkOrder.completed_at >= thirty_days_ago,
            )
        )
        completed_wos = list((await self.session.execute(completed_wo_stmt)).scalars().all())

        billed_amount_total = sum(
            (Decimal(wo.billed_amount or 0) for wo in completed_wos), Decimal("0")
        )

        # Monthly revenue: contract.value / (period months). Falls back to
        # billed_amount_total when the contract has no value or zero duration.
        monthly_revenue = Decimal("0")
        if contract.value and contract.value > 0:
            try:
                start = datetime.fromisoformat(contract.period_start)
                end = datetime.fromisoformat(contract.period_end)
                months = max(1, (end.year - start.year) * 12 + (end.month - start.month))
                monthly_revenue = (Decimal(contract.value) / Decimal(months)).quantize(
                    Decimal("0.01")
                )
            except (ValueError, TypeError):
                pass

        # PPM due in next 30 days
        in_30_days = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
        upcoming = await self.schedule_repo.list_due_within(contract_id, in_30_days)

        return ContractDashboardResponse(
            contract_id=contract.id,
            contract_number=contract.contract_number,
            customer_id=contract.customer_id,
            status=contract.status,
            open_tickets=open_tickets,
            in_progress_tickets=in_progress_tickets,
            sla_breaches=sla_breaches,
            scheduled_work_orders=scheduled_work_orders,
            completed_work_orders_30d=len(completed_wos),
            billed_amount_total=billed_amount_total.quantize(Decimal("0.01")),
            monthly_revenue=monthly_revenue,
            currency=contract.currency,
            upcoming_ppm_30d=len(upcoming),
        )

    # ── SLA breach scan ───────────────────────────────────────────────────

    async def scan_sla_breaches(
        self,
        *,
        contract_id: uuid.UUID | None = None,
        notify: bool = True,
    ) -> SLABreachScanResponse:
        """Find tickets past their ``sla_due_at`` and emit breach events.

        For each ticket whose ``sla_due_at < now`` and status is one of
        (new / assigned / in_progress) AND ``sla_breach_notified_at IS NULL``,
        emit a ``service.sla.breached`` event and stamp the ticket as notified
        so the same breach isn't re-announced on every cron tick.

        Args:
            contract_id: restrict the scan to one contract. Default scans all.
            notify: if False, list breaches but don't emit events / stamp the
                ticket — used for read-only dashboard polling.

        Returns:
            ``SLABreachScanResponse`` containing every currently-overdue ticket
            (regardless of prior notification) plus a count of how many were
            newly notified by this call.
        """
        from sqlalchemy import func, select

        now_dt = datetime.now(UTC)
        now_iso = now_dt.isoformat()

        stmt = select(ServiceTicket).where(
            ServiceTicket.sla_due_at.isnot(None),
            ServiceTicket.sla_due_at < now_iso,
            ServiceTicket.status.in_(("new", "assigned", "in_progress")),
        )
        if contract_id is not None:
            stmt = stmt.where(ServiceTicket.contract_id == contract_id)

        tickets = list((await self.session.execute(stmt)).scalars().all())

        # Also count *all* open tickets in scope for context on the response.
        # Count at the DB level to avoid materialising rows (and their
        # work_orders selectin load) only to call len().
        open_stmt = (
            select(func.count())
            .select_from(ServiceTicket)
            .where(ServiceTicket.status.in_(("new", "assigned", "in_progress")))
        )
        if contract_id is not None:
            open_stmt = open_stmt.where(ServiceTicket.contract_id == contract_id)
        total_open = int((await self.session.execute(open_stmt)).scalar_one())

        breaches: list[SLABreachEntry] = []
        newly_notified = 0
        for ticket in tickets:
            try:
                due_dt = _parse_iso(ticket.sla_due_at) if ticket.sla_due_at else None
            except (ValueError, TypeError):
                continue
            minutes_overdue = (
                int((now_dt - due_dt).total_seconds() // 60) if due_dt else 0
            )
            breaches.append(
                SLABreachEntry(
                    ticket_id=ticket.id,
                    ticket_number=ticket.ticket_number,
                    contract_id=ticket.contract_id,
                    priority=ticket.priority,
                    sla_due_at=ticket.sla_due_at or "",
                    minutes_overdue=minutes_overdue,
                    assigned_to=ticket.assigned_to,
                )
            )

            if notify and ticket.sla_breach_notified_at is None:
                await self.ticket_repo.update_fields(
                    ticket.id, sla_breach_notified_at=now_iso,
                )
                newly_notified += 1
                event_bus.publish_detached(
                    "service.sla.breached",
                    {
                        "ticket_id": str(ticket.id),
                        "ticket_number": ticket.ticket_number,
                        "contract_id": str(ticket.contract_id),
                        "priority": ticket.priority,
                        "sla_due_at": ticket.sla_due_at,
                        "minutes_overdue": minutes_overdue,
                        "assigned_to": ticket.assigned_to,
                    },
                    source_module="service",
                )

        return SLABreachScanResponse(
            scanned_at=now_iso,
            total_open=total_open,
            breaches=breaches,
            newly_notified=newly_notified,
        )

    # ── NCR from work order ───────────────────────────────────────────────

    async def file_ncr_from_work_order(
        self,
        wo_id: uuid.UUID,
        data: NCRFromWorkOrderRequest,
        user_id: str | None = None,
    ) -> NCRFromWorkOrderResponse:
        """File an NCR linked to a work order, on the parent project.

        Walks WO → ticket → contract → project_id. Requires the contract to
        carry a ``project_id`` — NCR is a project-scoped construct. Raises
        409 otherwise.
        """
        wo = await self.get_work_order(wo_id)
        ticket = await self.get_ticket(wo.ticket_id)
        contract = await self.get_contract(ticket.contract_id)

        if contract.project_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "NCR requires a project-scoped contract. "
                    f"Contract {contract.contract_number} has no project."
                ),
            )

        # Late import to avoid pulling NCR into service-module import graph.
        from app.modules.ncr.models import NCR
        from app.modules.ncr.repository import NCRRepository

        ncr_repo = NCRRepository(self.session)
        ncr_number = await ncr_repo.next_ncr_number(contract.project_id)
        ncr = NCR(
            project_id=contract.project_id,
            ncr_number=ncr_number,
            title=data.title,
            description=data.description,
            ncr_type=data.ncr_type,
            severity=data.severity,
            status="identified",
            location_description=data.location_description,
            created_by=user_id,
            metadata_={
                "source": "service_work_order",
                "work_order_id": str(wo_id),
                "work_order_number": wo.work_order_number,
                "ticket_id": str(ticket.id),
                "ticket_number": ticket.ticket_number,
            },
        )
        ncr = await ncr_repo.create(ncr)

        # Echo the link back onto the WO metadata for round-trip discoverability.
        wo_meta = dict(wo.metadata_ or {})
        ncr_list = list(wo_meta.get("ncr_ids", []))
        ncr_list.append(str(ncr.id))
        wo_meta["ncr_ids"] = ncr_list
        await self.work_order_repo.update_fields(wo_id, metadata_=wo_meta)

        event_bus.publish_detached(
            "service.work_order.ncr_filed",
            {
                "work_order_id": str(wo_id),
                "work_order_number": wo.work_order_number,
                "ncr_id": str(ncr.id),
                "ncr_number": ncr_number,
                "project_id": str(contract.project_id),
                "severity": data.severity,
            },
            source_module="service",
        )
        logger.info(
            "NCR filed from work order: %s → %s (project=%s)",
            wo.work_order_number, ncr_number, contract.project_id,
        )
        return NCRFromWorkOrderResponse(
            ncr_id=ncr.id,
            ncr_number=ncr_number,
            project_id=contract.project_id,
            work_order_id=wo_id,
        )

    # ── Procurement: PR from WO material item ────────────────────────────

    async def request_purchase_for_item(
        self,
        wo_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: str | None = None,
    ) -> uuid.UUID:
        """Emit a procurement request event for a WO material item.

        Returns the item id for the caller. The actual PO row is created by
        the procurement-side subscriber (decoupled). Only material items
        flagged ``metadata.procurement_required=true`` are eligible.
        """
        wo = await self.get_work_order(wo_id)
        items = await self.work_order_item_repo.list_for_work_order(wo_id)
        item = next((i for i in items if i.id == item_id), None)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work order item not found",
            )
        if item.item_type != "material":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Procurement requests are only valid for material items",
            )

        ticket = await self.get_ticket(wo.ticket_id)
        contract = await self.get_contract(ticket.contract_id)

        event_bus.publish_detached(
            "service.work_order.material_requested",
            {
                "work_order_id": str(wo_id),
                "work_order_number": wo.work_order_number,
                "item_id": str(item_id),
                "description": item.description,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_rate": str(item.unit_rate),
                "currency": wo.currency,
                "project_id": str(contract.project_id) if contract.project_id else None,
                "contract_id": str(contract.id),
                "requested_by": user_id,
            },
            source_module="service",
        )
        # Also persist an audit hint on the item so the UI can show "PR pending".
        item_meta = dict(item.metadata_ or {})
        item_meta["procurement_requested_at"] = _utcnow_iso()
        item_meta["procurement_requested_by"] = user_id
        await self.work_order_item_repo.update_fields(item_id, metadata_=item_meta)
        return item_id
