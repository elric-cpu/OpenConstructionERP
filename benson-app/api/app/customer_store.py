import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from .domain import CustomerCreate, CustomerSummary, CustomerUpdate
from .store_base import StoreBase
from .storage_schema import audit_events, customers, leads

_SENSITIVE_CUSTOMER_FIELDS = {
    "billing_address",
    "email",
    "notes",
    "phone",
    "service_address",
}


def _audit_delta(current: Any, changes: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {
            "from": "[redacted]" if key in _SENSITIVE_CUSTOMER_FIELDS else current[key],
            "to": "[redacted]" if key in _SENSITIVE_CUSTOMER_FIELDS else value,
        }
        for key, value in changes.items()
        if current[key] != value
    }


class CustomerStoreMixin(StoreBase):
    def list_customers(
        self, *, query: str = "", include_archived: bool = False
    ) -> list[CustomerSummary]:
        statement = select(customers)
        if not include_archived:
            statement = statement.where(customers.c.status == "active")
        if query.strip():
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    customers.c.name.ilike(pattern),
                    customers.c.company.ilike(pattern),
                    customers.c.email.ilike(pattern),
                    customers.c.phone.ilike(pattern),
                    customers.c.city.ilike(pattern),
                )
            )
        with self.engine.connect() as db:
            rows = db.execute(statement.order_by(customers.c.name)).mappings().all()
        return [CustomerSummary.model_validate(dict(row)) for row in rows]

    def get_customer(self, customer_id: str) -> CustomerSummary | None:
        with self.engine.connect() as db:
            row = (
                db.execute(select(customers).where(customers.c.id == customer_id))
                .mappings()
                .first()
            )
        return CustomerSummary.model_validate(dict(row)) if row else None

    def list_customer_audit(self, customer_id: str) -> list[dict[str, Any]] | None:
        if self.get_customer(customer_id) is None:
            return None
        with self.engine.connect() as db:
            rows = (
                db.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.subject_type == "customer",
                        audit_events.c.subject_id == customer_id,
                    )
                    .order_by(audit_events.c.occurred_at.desc())
                )
                .mappings()
                .all()
            )
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def create_customer(
        self, customer: CustomerCreate, *, actor: str, source_lead_id: str | None = None
    ) -> CustomerSummary:
        customer_id = str(uuid4())
        now = datetime.now(UTC)
        values = customer.model_dump(mode="json") | {
            "id": customer_id,
            "status": "active",
            "source_lead_id": source_lead_id,
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as db:
                db.execute(customers.insert().values(**values))
                self._audit(
                    db,
                    event="customer.created",
                    actor=actor,
                    subject_type="customer",
                    subject_id=customer_id,
                    payload={"source_lead_id": source_lead_id},
                )
        except IntegrityError as error:
            raise ValueError("This lead is already linked to a customer") from error
        result = self.get_customer(customer_id)
        if result is None:
            raise RuntimeError("Created customer could not be loaded")
        return result

    def create_customer_from_lead(
        self, lead_id: str, *, actor: str
    ) -> CustomerSummary | None:
        with self.engine.connect() as db:
            lead = (
                db.execute(
                    select(leads).where(
                        leads.c.id == lead_id, leads.c.deleted_at.is_(None)
                    )
                )
                .mappings()
                .first()
            )
        if not lead:
            return None
        if lead["is_spam"] or lead["status"] not in {
            "qualified",
            "scheduled",
            "closed",
        }:
            raise ValueError("Only qualified non-spam leads can become customers")
        return self.create_customer(
            CustomerCreate(
                name=lead["name"],
                phone=lead["phone"],
                email=lead["email"],
                city=lead["city"],
                notes=f"Created from {lead['source']} lead.",
            ),
            actor=actor,
            source_lead_id=lead_id,
        )

    def update_customer(
        self, customer_id: str, change: CustomerUpdate, *, actor: str
    ) -> CustomerSummary | None:
        changes: dict[str, Any] = change.model_dump(exclude_unset=True, mode="json")
        with self.engine.begin() as db:
            current = (
                db.execute(select(customers).where(customers.c.id == customer_id))
                .mappings()
                .first()
            )
            if not current or current["status"] != "active":
                return None
            delta = _audit_delta(current, changes)
            if delta:
                db.execute(
                    update(customers)
                    .where(customers.c.id == customer_id)
                    .values(**changes, updated_at=datetime.now(UTC))
                )
                self._audit(
                    db,
                    event="customer.updated",
                    actor=actor,
                    subject_type="customer",
                    subject_id=customer_id,
                    payload={"delta": delta},
                )
        return self.get_customer(customer_id)

    def archive_customer(self, customer_id: str, *, actor: str) -> bool:
        with self.engine.begin() as db:
            result = db.execute(
                update(customers)
                .where(customers.c.id == customer_id, customers.c.status == "active")
                .values(status="archived", updated_at=datetime.now(UTC))
            )
            if result.rowcount:
                self._audit(
                    db,
                    event="customer.archived",
                    actor=actor,
                    subject_type="customer",
                    subject_id=customer_id,
                    payload={},
                )
        return bool(result.rowcount)
