import json
from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select, update

from .change_order_domain import (
    ChangeOrderCreate,
    ChangeOrderLineInput,
    ChangeOrderSummary,
    ChangeOrderUpdate,
)
from .schedule_store import lock_schedule_job
from .store_base import StoreBase
from .change_order_schema import (
    change_order_approvals,
    change_order_lines,
    change_orders,
)
from .storage_schema import audit_events, customers, field_reports, jobs

change_order_write_lock = RLock()


class ChangeOrderStaleWrite(ValueError):
    pass


def _line_rows(
    change_order_id: str, lines: list[ChangeOrderLineInput]
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    subtotal = 0
    for position, line in enumerate(lines, start=1):
        line_total = line.total_cents()
        subtotal += line_total
        rows.append(
            {
                "id": str(uuid4()),
                "change_order_id": change_order_id,
                "position": position,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit": line.unit,
                "unit_price_cents": line.unit_price_cents,
                "line_total_cents": line_total,
            }
        )
    return rows, subtotal


class ChangeOrderStoreMixin(StoreBase):
    def list_change_orders(
        self, *, job_id: str | None = None, status: str = ""
    ) -> list[ChangeOrderSummary]:
        statement = select(change_orders.c.id)
        if job_id:
            statement = statement.where(change_orders.c.job_id == job_id)
        if status:
            statement = statement.where(change_orders.c.status == status)
        with self.engine.connect() as db:
            ids = list(
                db.execute(
                    statement.order_by(change_orders.c.updated_at.desc())
                ).scalars()
            )
        return [self._load_change_order(order_id) for order_id in ids]

    def get_change_order(self, change_order_id: str) -> ChangeOrderSummary | None:
        with self.engine.connect() as db:
            exists = db.execute(
                select(change_orders.c.id).where(change_orders.c.id == change_order_id)
            ).first()
        return self._load_change_order(change_order_id) if exists else None

    def create_change_order(
        self, order: ChangeOrderCreate, *, actor: str
    ) -> ChangeOrderSummary:
        order_id = str(uuid4())
        root_id = order_id
        lines, subtotal = _line_rows(order_id, order.lines)
        now = datetime.now(UTC)
        with change_order_write_lock, self.engine.begin() as db:
            lock_schedule_job(db, str(order.job_id))
            job = (
                db.execute(select(jobs).where(jobs.c.id == str(order.job_id)))
                .mappings()
                .first()
            )
            if not job or job["status"] not in {"planned", "active", "on_hold"}:
                raise ValueError("Change orders require an open job")
            if order.originating_field_report_id:
                origin = db.execute(
                    select(field_reports.c.id).where(
                        field_reports.c.id == str(order.originating_field_report_id),
                        field_reports.c.job_id == str(order.job_id),
                    )
                ).first()
                if not origin:
                    raise ValueError(
                        "Originating field report does not belong to the job"
                    )
            number = f"CO-{job['number'].removeprefix('JOB-')}-{order_id[:8].upper()}"
            db.execute(
                change_orders.insert().values(
                    id=order_id,
                    root_id=root_id,
                    previous_revision_id=None,
                    revision=1,
                    number=number,
                    job_id=str(order.job_id),
                    estimate_id=job["estimate_id"],
                    customer_id=job["customer_id"],
                    originating_field_report_id=(
                        str(order.originating_field_report_id)
                        if order.originating_field_report_id
                        else None
                    ),
                    status="draft",
                    version=1,
                    title=order.title,
                    schedule_impact_days=order.schedule_impact_days,
                    internal_notes=order.internal_notes,
                    customer_explanation=order.customer_explanation,
                    subtotal_cents=subtotal,
                    created_by=actor,
                    submitted_by=None,
                    submitted_at=None,
                    decided_by=None,
                    decided_at=None,
                    decision_note=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(change_order_lines.insert(), lines)
            self._audit_change_order(
                db,
                order_id,
                "change_order.created",
                actor,
                {"number": number, "subtotal_cents": subtotal, "version": 1},
            )
        return self._load_change_order(order_id)

    def update_change_order(
        self, change_order_id: str, change: ChangeOrderUpdate, *, actor: str
    ) -> ChangeOrderSummary | None:
        changes = change.model_dump(
            exclude_unset=True,
            exclude={"expected_version", "lines"},
            mode="json",
        )
        with change_order_write_lock, self.engine.begin() as db:
            current = (
                db.execute(
                    select(change_orders).where(change_orders.c.id == change_order_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            if current["status"] != "draft":
                raise ValueError("Submitted change order revisions are immutable")
            line_count = None
            if change.lines is not None:
                lines, subtotal = _line_rows(change_order_id, change.lines)
                changes["subtotal_cents"] = subtotal
                line_count = len(lines)
            changed = db.execute(
                update(change_orders)
                .where(
                    change_orders.c.id == change_order_id,
                    change_orders.c.status == "draft",
                    change_orders.c.version == change.expected_version,
                )
                .values(
                    **changes,
                    version=change.expected_version + 1,
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                raise ChangeOrderStaleWrite(
                    "Change order changed; reload before retrying"
                )
            if change.lines is not None:
                db.execute(
                    delete(change_order_lines).where(
                        change_order_lines.c.change_order_id == change_order_id
                    )
                )
                db.execute(change_order_lines.insert(), lines)
            self._audit_change_order(
                db,
                change_order_id,
                "change_order.updated",
                actor,
                {
                    "changed_fields": sorted(changes),
                    "line_count": line_count,
                    "from_version": change.expected_version,
                    "to_version": change.expected_version + 1,
                },
            )
        return self._load_change_order(change_order_id)

    def transition_change_order(
        self,
        change_order_id: str,
        *,
        target: str,
        expected_version: int,
        note: str,
        actor: str,
    ) -> ChangeOrderSummary | None:
        with change_order_write_lock, self.engine.begin() as db:
            current = (
                db.execute(
                    select(change_orders).where(change_orders.c.id == change_order_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            transitions = {
                "draft": {"submitted", "void"},
                "submitted": {"approved", "rejected", "void"},
                "approved": set(),
                "rejected": set(),
                "void": set(),
            }
            if target not in transitions[current["status"]]:
                raise ValueError(
                    f"Change order cannot move from {current['status']} to {target}"
                )
            lock_schedule_job(db, current["job_id"])
            now = datetime.now(UTC)
            values: dict[str, Any] = {
                "status": target,
                "version": expected_version + 1,
                "updated_at": now,
            }
            if target == "submitted":
                values |= {"submitted_by": actor, "submitted_at": now}
            if target in {"approved", "rejected"}:
                values |= {
                    "decided_by": actor,
                    "decided_at": now,
                    "decision_note": note.strip(),
                }
            changed = db.execute(
                update(change_orders)
                .where(
                    change_orders.c.id == change_order_id,
                    change_orders.c.status == current["status"],
                    change_orders.c.version == expected_version,
                )
                .values(**values)
            )
            if changed.rowcount != 1:
                raise ChangeOrderStaleWrite(
                    "Change order changed; reload before retrying"
                )
            if target in {"approved", "rejected"}:
                db.execute(
                    change_order_approvals.insert().values(
                        id=str(uuid4()),
                        change_order_id=change_order_id,
                        decision=target,
                        note=note.strip(),
                        actor=actor,
                        occurred_at=now,
                    )
                )
            contract_delta = 0
            if target == "approved":
                previous_approved = db.execute(
                    select(change_orders.c.subtotal_cents)
                    .where(
                        change_orders.c.root_id == current["root_id"],
                        change_orders.c.id != change_order_id,
                        change_orders.c.status == "approved",
                    )
                    .order_by(change_orders.c.revision.desc())
                    .limit(1)
                ).scalar_one_or_none()
                contract_delta = current["subtotal_cents"] - (previous_approved or 0)
                job = (
                    db.execute(select(jobs).where(jobs.c.id == current["job_id"]))
                    .mappings()
                    .one()
                )
                next_contract = job["contract_value_cents"] + contract_delta
                next_approved = job["approved_change_order_cents"] + contract_delta
                next_billable = job["billing_eligible_cents"] + contract_delta
                if min(next_contract, next_approved, next_billable) < 0:
                    raise ValueError("Approved revision would make job totals negative")
                db.execute(
                    update(jobs)
                    .where(jobs.c.id == current["job_id"])
                    .values(
                        contract_value_cents=next_contract,
                        approved_change_order_cents=next_approved,
                        billing_eligible_cents=next_billable,
                        updated_at=now,
                    )
                )
                self._audit(
                    db,
                    event="job.change_order_approved",
                    actor=actor,
                    subject_type="job",
                    subject_id=current["job_id"],
                    payload={
                        "change_order_id": change_order_id,
                        "contract_delta_cents": contract_delta,
                        "contract_value_cents": next_contract,
                        "billing_eligible_cents": next_billable,
                    },
                )
            self._audit_change_order(
                db,
                change_order_id,
                "change_order.status_changed",
                actor,
                {
                    "from": current["status"],
                    "to": target,
                    "from_version": expected_version,
                    "to_version": expected_version + 1,
                    "contract_delta_cents": contract_delta,
                },
            )
        return self._load_change_order(change_order_id)

    def create_change_order_revision(
        self,
        change_order_id: str,
        *,
        expected_version: int,
        reason: str,
        actor: str,
    ) -> ChangeOrderSummary | None:
        revision_id = str(uuid4())
        with change_order_write_lock, self.engine.begin() as db:
            current = (
                db.execute(
                    select(change_orders).where(change_orders.c.id == change_order_id)
                )
                .mappings()
                .first()
            )
            if not current:
                return None
            if current["status"] not in {"approved", "rejected"}:
                raise ValueError("Only decided change orders may be revised")
            if current["version"] != expected_version:
                raise ChangeOrderStaleWrite(
                    "Change order changed; reload before retrying"
                )
            if db.execute(
                select(change_orders.c.id).where(
                    change_orders.c.previous_revision_id == change_order_id
                )
            ).first():
                raise ValueError("A linked revision already exists")
            lines = (
                db.execute(
                    select(change_order_lines)
                    .where(change_order_lines.c.change_order_id == change_order_id)
                    .order_by(change_order_lines.c.position)
                )
                .mappings()
                .all()
            )
            now = datetime.now(UTC)
            revision = current["revision"] + 1
            db.execute(
                change_orders.insert().values(
                    id=revision_id,
                    root_id=current["root_id"],
                    previous_revision_id=change_order_id,
                    revision=revision,
                    number=f"{current['number'].split('-R', 1)[0]}-R{revision}",
                    job_id=current["job_id"],
                    estimate_id=current["estimate_id"],
                    customer_id=current["customer_id"],
                    originating_field_report_id=current["originating_field_report_id"],
                    status="draft",
                    version=1,
                    title=current["title"],
                    schedule_impact_days=current["schedule_impact_days"],
                    internal_notes=current["internal_notes"],
                    customer_explanation=current["customer_explanation"],
                    subtotal_cents=current["subtotal_cents"],
                    created_by=actor,
                    submitted_by=None,
                    submitted_at=None,
                    decided_by=None,
                    decided_at=None,
                    decision_note=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.execute(
                change_order_lines.insert(),
                [
                    {
                        **{
                            key: line[key]
                            for key in (
                                "position",
                                "description",
                                "quantity",
                                "unit",
                                "unit_price_cents",
                                "line_total_cents",
                            )
                        },
                        "id": str(uuid4()),
                        "change_order_id": revision_id,
                    }
                    for line in lines
                ],
            )
            self._audit_change_order(
                db,
                revision_id,
                "change_order.revision_created",
                actor,
                {"previous_revision_id": change_order_id, "reason": reason.strip()},
            )
        return self._load_change_order(revision_id)

    def list_change_order_audit(
        self, change_order_id: str
    ) -> list[dict[str, Any]] | None:
        with self.engine.connect() as db:
            if not db.execute(
                select(change_orders.c.id).where(change_orders.c.id == change_order_id)
            ).first():
                return None
            rows = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "change_order",
                        audit_events.c.subject_id == change_order_id,
                    )
                    .order_by(audit_events.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def _load_change_order(self, change_order_id: str) -> ChangeOrderSummary:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(
                        change_orders,
                        jobs.c.number.label("job_number"),
                        jobs.c.title.label("job_title"),
                        customers.c.name.label("customer_name"),
                    )
                    .join(jobs, jobs.c.id == change_orders.c.job_id)
                    .join(customers, customers.c.id == change_orders.c.customer_id)
                    .where(change_orders.c.id == change_order_id)
                )
                .mappings()
                .one()
            )
            lines = (
                db.execute(
                    select(change_order_lines)
                    .where(change_order_lines.c.change_order_id == change_order_id)
                    .order_by(change_order_lines.c.position)
                )
                .mappings()
                .all()
            )
        payload = dict(row)
        payload["lines"] = [
            {
                **{
                    key: line[key]
                    for key in (
                        "id",
                        "position",
                        "description",
                        "unit",
                        "unit_price_cents",
                        "line_total_cents",
                    )
                },
                "quantity": Decimal(line["quantity"]),
            }
            for line in lines
        ]
        return ChangeOrderSummary.model_validate(payload)

    def _audit_change_order(
        self,
        db: Any,
        change_order_id: str,
        event: str,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        self._audit(
            db,
            event=event,
            actor=actor,
            subject_type="change_order",
            subject_id=change_order_id,
            payload=payload,
        )
