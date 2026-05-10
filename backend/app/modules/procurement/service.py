"""‌⁠‍Procurement service — business logic for purchase orders and goods receipts.

Stateless service layer.

Event publishing (slice E):
    procurement.po.created      — new PO row inserted
    procurement.po.updated      — PO fields changed (incl. status transition)
    procurement.po.issued       — PO transitioned to 'issued'
    procurement.gr.created      — new goods receipt inserted
    procurement.gr.confirmed    — goods receipt confirmed (may flip PO status)
"""

import logging
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.procurement.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.modules.procurement.repository import (
    GoodsReceiptRepository,
    GRItemRepository,
    POItemRepository,
    PurchaseOrderRepository,
)
from app.modules.procurement.schemas import (
    GRCreate,
    POCreate,
    POUpdate,
    ProcurementStatsResponse,
)

logger = logging.getLogger(__name__)
_logger_ev = logging.getLogger(__name__ + ".events")


async def _safe_publish(name: str, data: dict, source_module: str = "oe_procurement") -> None:
    """‌⁠‍Best-effort event publish — never blocks the caller on failure."""
    try:
        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception:
        _logger_ev.debug("Event publish skipped: %s", name)

# ── Allowed PO status transitions ───────────────────────────────────────────

_PO_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"issued", "cancelled"},
    "issued": {"partially_received", "completed", "cancelled"},
    "partially_received": {"completed", "cancelled"},
    "completed": set(),  # terminal
    "cancelled": {"draft"},  # allow re-opening
}

_VALID_PO_STATUSES = set(_PO_STATUS_TRANSITIONS.keys())


def _parse_decimal(value: str, field_name: str = "value") -> Decimal:
    """‌⁠‍Parse a string to Decimal, raising a clear error on failure."""
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid numeric value for {field_name}: {value!r}",
        ) from exc


def _compute_po_total(subtotal: str, tax: str) -> str:
    """Compute amount_total = amount_subtotal + tax_amount."""
    s = _parse_decimal(subtotal, "amount_subtotal")
    t = _parse_decimal(tax, "tax_amount")
    return str(s + t)


def _validate_3way_match(
    po: PurchaseOrder,
    invoice_lines: list[dict],
) -> list[dict]:
    """Run 3-way match (PO ↔ GR ↔ Invoice) per PO line.

    For each PO line, sums ``quantity_received`` over GR items belonging to
    confirmed goods receipts. Any invoice line whose proposed quantity exceeds
    the matched received quantity is reported.

    ``invoice_lines`` is a list of dicts with keys:
        - ``po_item_id``: UUID of the PO line being invoiced (None = unmatched)
        - ``quantity``: proposed invoice quantity (string-decimal)
        - ``description``: line description (for the error payload)
        - ``ordinal``: 0-based index in the invoice (for the error payload)

    Returns a list of violation dicts (empty list = clean match). Lines without
    a ``po_item_id`` are skipped (free-text additions are out of scope).
    """
    received_by_po_item: dict[uuid.UUID, Decimal] = {}
    for gr in po.goods_receipts or []:
        if gr.status != "confirmed":
            continue
        for gr_item in gr.items or []:
            if gr_item.po_item_id is None:
                continue
            try:
                qty = Decimal(str(gr_item.quantity_received or "0"))
            except (InvalidOperation, ValueError, TypeError):
                qty = Decimal("0")
            received_by_po_item[gr_item.po_item_id] = (
                received_by_po_item.get(gr_item.po_item_id, Decimal("0")) + qty
            )

    po_items_by_id = {item.id: item for item in (po.items or [])}

    has_invoice_qty = any(
        (line.get("po_item_id") is not None
         and _to_decimal(line.get("quantity")) > Decimal("0"))
        for line in invoice_lines
    )
    if not received_by_po_item and (po.items or []) and has_invoice_qty:
        return [{
            "ordinal": None,
            "po_item_id": None,
            "description": None,
            "requested_qty": None,
            "received_qty": "0",
            "reason": "no_confirmed_grs",
            "message": (
                "No confirmed goods receipts exist for this PO; "
                "pass force=true to invoice without GR match."
            ),
        }]

    violations: list[dict] = []
    for line in invoice_lines:
        po_item_id = line.get("po_item_id")
        if po_item_id is None:
            continue
        po_item = po_items_by_id.get(po_item_id)
        if po_item is None:
            continue
        requested = _to_decimal(line.get("quantity"))
        received = received_by_po_item.get(po_item_id, Decimal("0"))
        if requested > received:
            violations.append({
                "ordinal": line.get("ordinal"),
                "po_item_id": str(po_item_id),
                "description": po_item.description,
                "requested_qty": str(requested),
                "received_qty": str(received),
            })

    return violations


def _to_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


class ProcurementService:
    """Business logic for procurement operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.po_repo = PurchaseOrderRepository(session)
        self.po_item_repo = POItemRepository(session)
        self.gr_repo = GoodsReceiptRepository(session)
        self.gr_item_repo = GRItemRepository(session)

    # ── Purchase Orders ──────────────────────────────────────────────────────

    async def create_po(
        self,
        data: POCreate,
        user_id: str | None = None,
    ) -> PurchaseOrder:
        """Create a new purchase order with optional line items.

        Automatically computes amount_total = amount_subtotal + tax_amount.
        When ``items`` are supplied, ``amount_subtotal`` is re-aggregated as
        ``sum(quantity * unit_rate)`` so the PO totals always agree with the
        line items the caller actually persisted (BUG-015).
        """
        # Validate initial status
        if data.status not in _VALID_PO_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid PO status: '{data.status}'. "
                    f"Allowed: {', '.join(sorted(_VALID_PO_STATUSES))}"
                ),
            )

        # Re-aggregate subtotal from items when items are supplied. Each item's
        # own ``amount`` is also normalised to ``quantity * unit_rate`` if the
        # caller passed the schema default of "0".
        item_amounts: list[Decimal] = []
        for item_data in data.items:
            qty = _parse_decimal(item_data.quantity, "item.quantity")
            rate = _parse_decimal(item_data.unit_rate, "item.unit_rate")
            line_total = qty * rate
            existing = _parse_decimal(item_data.amount, "item.amount")
            if existing == Decimal("0"):
                item_data.amount = str(line_total)
            item_amounts.append(line_total)

        if data.items:
            aggregated_subtotal = str(sum(item_amounts, Decimal("0")))
            data.amount_subtotal = aggregated_subtotal

        # Server-side total computation
        computed_total = _compute_po_total(data.amount_subtotal, data.tax_amount)

        explicit_po_number = data.po_number
        # Mirrors changeorders BUG-354: MAX(po_number)+1 is not atomic, so two
        # concurrent creates can compute the same suffix and one would 500 on the
        # uq_procurement_po_project_number constraint. Retry by re-reading MAX.
        _MAX_RETRIES = 5
        last_exc: Exception | None = None
        po: PurchaseOrder | None = None
        for _attempt in range(_MAX_RETRIES):
            po_number = explicit_po_number or await self.po_repo.next_po_number(
                data.project_id,
            )
            po = PurchaseOrder(
                project_id=data.project_id,
                vendor_contact_id=data.vendor_contact_id,
                po_number=po_number,
                po_type=data.po_type,
                issue_date=data.issue_date,
                delivery_date=data.delivery_date,
                currency_code=data.currency_code,
                amount_subtotal=data.amount_subtotal,
                tax_amount=data.tax_amount,
                amount_total=computed_total,
                status=data.status,
                payment_terms=data.payment_terms,
                notes=data.notes,
                created_by=uuid.UUID(user_id) if user_id else None,
                metadata_=data.metadata,
            )
            try:
                po = await self.po_repo.create(po)
                break
            except IntegrityError as exc:
                last_exc = exc
                await self.session.rollback()
                if explicit_po_number:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Purchase order number '{explicit_po_number}' already "
                            f"exists for this project."
                        ),
                    ) from exc
                continue
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Could not generate a unique PO number after "
                    f"{_MAX_RETRIES} attempts (concurrent contention). Please retry."
                ),
            ) from last_exc

        assert po is not None  # loop guarantees assignment on the break path

        # Create line items
        for idx, item_data in enumerate(data.items):
            item = PurchaseOrderItem(
                po_id=po.id,
                description=item_data.description,
                quantity=item_data.quantity,
                unit=item_data.unit,
                unit_rate=item_data.unit_rate,
                amount=item_data.amount,
                wbs_id=item_data.wbs_id,
                cost_category=item_data.cost_category,
                sort_order=item_data.sort_order if item_data.sort_order else idx,
            )
            await self.po_item_repo.create(item)

        # Reload the PO so the freshly inserted line items are populated on the
        # ``items`` relationship. ``po_repo.create`` refreshed the PO BEFORE the
        # items were inserted, so without this re-fetch the response would carry
        # an empty ``items: []`` collection (BUG-015).
        if data.items:
            reloaded = await self.po_repo.get(po.id)
            if reloaded is not None:
                po = reloaded

        await _safe_publish(
            "procurement.po.created",
            {
                "po_id": str(po.id),
                "project_id": str(po.project_id),
                "po_number": po.po_number,
                "po_type": po.po_type,
                "status": po.status,
                "vendor_contact_id": str(po.vendor_contact_id) if po.vendor_contact_id else None,
                "amount_total": po.amount_total,
                "currency_code": po.currency_code,
                "item_count": len(data.items),
            },
        )

        logger.info("PO created: %s (type=%s)", po.po_number, po.po_type)
        return po

    async def get_po(self, po_id: uuid.UUID) -> PurchaseOrder:
        """Get PO by ID. Raises 404 if not found."""
        po = await self.po_repo.get(po_id)
        if po is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase order not found",
            )
        return po

    async def list_pos(
        self,
        *,
        project_id: uuid.UUID | None = None,
        po_status: str | None = None,
        vendor_contact_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PurchaseOrder], int]:
        """List POs with filters."""
        return await self.po_repo.list(
            project_id=project_id,
            status=po_status,
            vendor_contact_id=vendor_contact_id,
            limit=limit,
            offset=offset,
        )

    async def update_po(
        self,
        po_id: uuid.UUID,
        data: POUpdate,
    ) -> PurchaseOrder:
        """Update PO fields and optionally replace items.

        Validates status transitions and recomputes amount_total when
        subtotal or tax are changed.
        """
        po = await self.get_po(po_id)  # 404 check

        fields = data.model_dump(exclude_unset=True, exclude={"items"})
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        # Validate status transition if status is being changed
        if "status" in fields and fields["status"] is not None:
            new_status = fields["status"]
            if new_status not in _VALID_PO_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Invalid PO status: '{new_status}'. "
                        f"Allowed: {', '.join(sorted(_VALID_PO_STATUSES))}"
                    ),
                )
            allowed = _PO_STATUS_TRANSITIONS.get(po.status, set())
            if new_status != po.status and new_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot transition PO from '{po.status}' to '{new_status}'. "
                        f"Allowed transitions: {', '.join(sorted(allowed)) or 'none'}"
                    ),
                )

        # Recompute total if subtotal or tax changed
        new_subtotal = fields.get("amount_subtotal", po.amount_subtotal)
        new_tax = fields.get("tax_amount", po.tax_amount)
        if "amount_subtotal" in fields or "tax_amount" in fields:
            fields["amount_total"] = _compute_po_total(
                new_subtotal or po.amount_subtotal,
                new_tax or po.tax_amount,
            )

        if fields:
            await self.po_repo.update(po_id, **fields)

        # Replace items if provided
        if data.items is not None:
            await self.po_item_repo.delete_by_po(po_id)
            for idx, item_data in enumerate(data.items):
                item = PurchaseOrderItem(
                    po_id=po_id,
                    description=item_data.description,
                    quantity=item_data.quantity,
                    unit=item_data.unit,
                    unit_rate=item_data.unit_rate,
                    amount=item_data.amount,
                    wbs_id=item_data.wbs_id,
                    cost_category=item_data.cost_category,
                    sort_order=item_data.sort_order if item_data.sort_order else idx,
                )
                await self.po_item_repo.create(item)

        updated = await self.po_repo.get(po_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase order not found",
            )

        await _safe_publish(
            "procurement.po.updated",
            {
                "po_id": str(po_id),
                "project_id": str(updated.project_id),
                "updated_fields": list(fields.keys()),
                "status": updated.status,
            },
        )

        logger.info("PO updated: %s", po_id)
        return updated

    async def issue_po(self, po_id: uuid.UUID) -> PurchaseOrder:
        """Transition PO to issued status."""
        po = await self.get_po(po_id)
        if po.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot issue PO in status '{po.status}'",
            )
        await self.po_repo.update(po_id, status="issued")
        updated = await self.po_repo.get(po_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase order not found",
            )

        await _safe_publish(
            "procurement.po.issued",
            {
                "po_id": str(po_id),
                "project_id": str(updated.project_id),
                "po_number": updated.po_number,
                "amount_total": updated.amount_total,
                "currency_code": updated.currency_code or "",
            },
        )

        logger.info("PO issued: %s", po.po_number)
        return updated

    # ── Goods Receipts ───────────────────────────────────────────────────────

    async def create_goods_receipt(
        self,
        data: GRCreate,
        user_id: str | None = None,
    ) -> GoodsReceipt:
        """Create a goods receipt against a PO.

        Validates:
        - PO exists and is in a receivable status (issued or partially_received)
        - received_qty <= ordered_qty for each GR item (when po_item_id provided)
        """
        po = await self.get_po(data.po_id)  # 404 check

        # PO must be in a status that accepts goods receipts
        if po.status not in ("issued", "partially_received"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot create goods receipt for PO in status '{po.status}'. "
                    "PO must be issued or partially_received."
                ),
            )

        # Validate GR item quantities against PO items
        po_items_by_id = {item.id: item for item in po.items}
        for item_data in data.items:
            if item_data.po_item_id is not None:
                po_item = po_items_by_id.get(item_data.po_item_id)
                if po_item is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"PO item {item_data.po_item_id} not found "
                            f"in purchase order {data.po_id}"
                        ),
                    )
                # Validate received quantity does not exceed ordered quantity
                try:
                    ordered = Decimal(po_item.quantity)
                    received = Decimal(item_data.quantity_received)
                except (InvalidOperation, ValueError, TypeError):
                    continue  # let DB-level validation handle bad numbers
                if received > ordered:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Received quantity ({received}) exceeds ordered quantity "
                            f"({ordered}) for PO item '{po_item.description}'"
                        ),
                    )

        gr = GoodsReceipt(
            po_id=data.po_id,
            receipt_date=data.receipt_date,
            received_by_id=data.received_by_id or (uuid.UUID(user_id) if user_id else None),
            delivery_note_number=data.delivery_note_number,
            status=data.status,
            notes=data.notes,
            metadata_=data.metadata,
        )
        gr = await self.gr_repo.create(gr)

        # Create GR items
        for item_data in data.items:
            item = GoodsReceiptItem(
                receipt_id=gr.id,
                po_item_id=item_data.po_item_id,
                quantity_ordered=item_data.quantity_ordered,
                quantity_received=item_data.quantity_received,
                quantity_rejected=item_data.quantity_rejected,
                rejection_reason=item_data.rejection_reason,
            )
            await self.gr_item_repo.create(item)

        await _safe_publish(
            "procurement.gr.created",
            {
                "gr_id": str(gr.id),
                "po_id": str(gr.po_id),
                "project_id": str(po.project_id),
                "status": gr.status,
                "item_count": len(data.items),
            },
        )

        logger.info("GR created for PO %s (date=%s)", data.po_id, data.receipt_date)
        return gr

    async def get_goods_receipt(self, gr_id: uuid.UUID) -> GoodsReceipt:
        """Get goods receipt by ID. Raises 404 if not found."""
        gr = await self.gr_repo.get(gr_id)
        if gr is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Goods receipt not found",
            )
        return gr

    async def list_goods_receipts(
        self,
        *,
        po_id: uuid.UUID | None = None,
        gr_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GoodsReceipt], int]:
        """List goods receipts with optional filters."""
        return await self.gr_repo.list(
            po_id=po_id, status=gr_status, limit=limit, offset=offset
        )

    async def confirm_goods_receipt(self, gr_id: uuid.UUID) -> GoodsReceipt:
        """Confirm a goods receipt and update the PO status accordingly.

        After confirmation, checks whether ALL PO items are fully received:
        - If fully received -> PO status = 'completed'
        - If partially received -> PO status = 'partially_received'
        """
        gr = await self.get_goods_receipt(gr_id)
        if gr.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot confirm goods receipt in status '{gr.status}'",
            )
        await self.gr_repo.update(gr_id, status="confirmed")

        # Update PO status based on total received quantities
        po = await self.get_po(gr.po_id)
        if po.status in ("issued", "partially_received"):
            all_fully_received = self._check_po_fully_received(po)
            if all_fully_received:
                await self.po_repo.update(po.id, status="completed")
                logger.info("PO %s fully received, status -> completed", po.po_number)
            elif po.status == "issued":
                await self.po_repo.update(po.id, status="partially_received")
                logger.info("PO %s partially received", po.po_number)

        updated = await self.gr_repo.get(gr_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Goods receipt not found",
            )

        # Compute the value of this receipt as Σ(quantity_received × po_item.unit_rate).
        # Finance subscribers need this to flip the matching slice of
        # ProjectBudget.committed → actual on each GR.
        po_items_by_id: dict[uuid.UUID, PurchaseOrderItem] = {it.id: it for it in po.items}
        gr_amount = Decimal("0")
        for gr_item in updated.items:
            if gr_item.po_item_id is None:
                continue
            po_item = po_items_by_id.get(gr_item.po_item_id)
            if po_item is None:
                continue
            try:
                qty = Decimal(str(gr_item.quantity_received or "0"))
                rate = Decimal(str(po_item.unit_rate or "0"))
            except (InvalidOperation, ValueError, TypeError):
                continue
            gr_amount += qty * rate

        await _safe_publish(
            "procurement.gr.confirmed",
            {
                "gr_id": str(gr_id),
                "po_id": str(updated.po_id),
                "project_id": str(po.project_id),
                "amount": str(gr_amount),
                "currency_code": po.currency_code or "",
            },
        )

        logger.info("GR confirmed: %s", gr_id)
        return updated

    # ── Stats ───────────────────────────────────────────────────────────────

    async def get_stats(self, project_id: uuid.UUID) -> ProcurementStatsResponse:
        """Return aggregate procurement statistics for a project."""
        raw = await self.po_repo.stats_for_project(project_id)
        return ProcurementStatsResponse(
            total_pos=raw["total_pos"],
            by_status=raw["by_status"],
            total_committed=raw["total_committed"],
            total_received=raw["total_received"],
            pending_delivery_count=raw["pending_delivery_count"],
        )

    @staticmethod
    def _check_po_fully_received(po: PurchaseOrder) -> bool:
        """Check if all PO items have been fully received across confirmed GRs."""
        if not po.items:
            return True

        # Sum confirmed received quantities per PO item
        received_by_item: dict[uuid.UUID, Decimal] = {}
        for gr in po.goods_receipts:
            if gr.status != "confirmed":
                continue
            for gr_item in gr.items:
                if gr_item.po_item_id is not None:
                    try:
                        qty = Decimal(gr_item.quantity_received)
                    except (InvalidOperation, ValueError, TypeError):
                        qty = Decimal("0")
                    received_by_item[gr_item.po_item_id] = (
                        received_by_item.get(gr_item.po_item_id, Decimal("0")) + qty
                    )

        # Check each PO item
        for po_item in po.items:
            try:
                ordered = Decimal(po_item.quantity)
            except (InvalidOperation, ValueError, TypeError):
                ordered = Decimal("0")
            received = received_by_item.get(po_item.id, Decimal("0"))
            if received < ordered:
                return False

        return True
