import json
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select, update

from .domain import EstimateCreate, EstimateLineInput, EstimateSummary, EstimateUpdate
from .store_base import StoreBase
from .storage_schema import audit_events, customers, estimate_lines, estimates


def _line_values(
    estimate_id: str, lines: list[EstimateLineInput]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    subtotal = 0
    for position, line in enumerate(lines, start=1):
        line_total = int(
            (line.quantity * line.unit_price_cents).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        subtotal += line_total
        rows.append(
            {
                "id": str(uuid4()),
                "estimate_id": estimate_id,
                "position": position,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit": line.unit,
                "unit_price_cents": line.unit_price_cents,
                "line_total_cents": line_total,
            }
        )
    return rows, subtotal


class EstimateStoreMixin(StoreBase):
    def list_estimates(self, *, status: str = "") -> list[EstimateSummary]:
        statement = select(estimates)
        if status:
            statement = statement.where(estimates.c.status == status)
        with self.engine.connect() as db:
            rows = (
                db.execute(statement.order_by(estimates.c.updated_at.desc()))
                .mappings()
                .all()
            )
        return [self._load_estimate(row["id"]) for row in rows]

    def _load_estimate(self, estimate_id: str) -> EstimateSummary:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(estimates, customers.c.name.label("customer_name"))
                    .join(customers, customers.c.id == estimates.c.customer_id)
                    .where(estimates.c.id == estimate_id)
                )
                .mappings()
                .one()
            )
            lines = (
                db.execute(
                    select(estimate_lines)
                    .where(estimate_lines.c.estimate_id == estimate_id)
                    .order_by(estimate_lines.c.position)
                )
                .mappings()
                .all()
            )
        payload = dict(row)
        payload["lines"] = [
            {**dict(line), "quantity": Decimal(line["quantity"])} for line in lines
        ]
        return EstimateSummary.model_validate(payload)

    def list_estimate_audit(self, estimate_id: str) -> list[dict[str, Any]] | None:
        with self.engine.connect() as db:
            exists = db.execute(
                select(estimates.c.id).where(estimates.c.id == estimate_id)
            ).first()
            if not exists:
                return None
            rows = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "estimate",
                        audit_events.c.subject_id == estimate_id,
                    )
                    .order_by(audit_events.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def create_estimate(
        self, estimate: EstimateCreate, *, actor: str
    ) -> EstimateSummary:
        estimate_id = str(uuid4())
        number = f"EST-{datetime.now(UTC).year}-{estimate_id[:8].upper()}"
        line_rows, subtotal = _line_values(estimate_id, estimate.lines)
        now = datetime.now(UTC)
        with self.engine.begin() as db:
            customer = db.execute(
                select(customers.c.id).where(
                    customers.c.id == str(estimate.customer_id),
                    customers.c.status == "active",
                )
            ).first()
            if not customer:
                raise ValueError("Estimate customer must be active")
            db.execute(
                estimates.insert().values(
                    id=estimate_id,
                    number=number,
                    customer_id=str(estimate.customer_id),
                    title=estimate.title,
                    scope_notes=estimate.scope_notes,
                    valid_until=estimate.valid_until,
                    status="draft",
                    version=1,
                    subtotal_cents=subtotal,
                    total_cents=subtotal,
                    created_by=actor,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(estimate_lines.insert(), line_rows)
            self._audit(
                db,
                event="estimate.created",
                actor=actor,
                subject_type="estimate",
                subject_id=estimate_id,
                payload={"number": number, "total_cents": subtotal},
            )
        return self._load_estimate(estimate_id)

    def update_estimate(
        self, estimate_id: str, change: EstimateUpdate, *, actor: str
    ) -> EstimateSummary | None:
        changes = change.model_dump(exclude_unset=True, exclude={"lines"}, mode="json")
        with self.engine.begin() as db:
            current = (
                db.execute(select(estimates).where(estimates.c.id == estimate_id))
                .mappings()
                .first()
            )
            if not current or current["status"] != "draft":
                return None
            line_count = None
            if change.lines is not None:
                line_rows, subtotal = _line_values(estimate_id, change.lines)
                db.execute(
                    delete(estimate_lines).where(
                        estimate_lines.c.estimate_id == estimate_id
                    )
                )
                db.execute(estimate_lines.insert(), line_rows)
                changes |= {"subtotal_cents": subtotal, "total_cents": subtotal}
                line_count = len(line_rows)
            db.execute(
                update(estimates)
                .where(estimates.c.id == estimate_id)
                .values(
                    **changes,
                    version=current["version"] + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            self._audit(
                db,
                event="estimate.updated",
                actor=actor,
                subject_type="estimate",
                subject_id=estimate_id,
                payload={"changed_fields": sorted(changes), "line_count": line_count},
            )
        return self._load_estimate(estimate_id)

    def transition_estimate(
        self,
        estimate_id: str,
        *,
        target: str,
        actor: str,
        delivery_confirmed: bool,
        note: str,
    ) -> EstimateSummary | None:
        from .domain import ESTIMATE_TRANSITIONS

        with self.engine.begin() as db:
            current = (
                db.execute(select(estimates).where(estimates.c.id == estimate_id))
                .mappings()
                .first()
            )
            if not current:
                return None
            if target not in ESTIMATE_TRANSITIONS[current["status"]]:
                raise ValueError(
                    f"Estimate cannot move from {current['status']} to {target}"
                )
            if target in {"ready", "sent"}:
                customer = db.execute(
                    select(customers.c.status).where(
                        customers.c.id == current["customer_id"]
                    )
                ).scalar_one()
                if customer != "active":
                    raise ValueError("An archived customer estimate cannot advance")
            if target == "sent" and not delivery_confirmed:
                raise ValueError(
                    "Confirm external delivery before marking an estimate sent"
                )
            db.execute(
                update(estimates)
                .where(estimates.c.id == estimate_id)
                .values(status=target, updated_at=datetime.now(UTC))
            )
            self._audit(
                db,
                event="estimate.status_changed",
                actor=actor,
                subject_type="estimate",
                subject_id=estimate_id,
                payload={
                    "from": current["status"],
                    "to": target,
                    "delivery_confirmed": delivery_confirmed,
                    "note_recorded": bool(note.strip()),
                },
            )
        return self._load_estimate(estimate_id)
