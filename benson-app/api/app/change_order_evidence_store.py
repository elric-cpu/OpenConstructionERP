from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from .change_order_domain import ChangeOrderEvidenceSummary
from .change_order_schema import change_order_evidence, change_orders
from .change_order_store import change_order_write_lock
from .store_base import StoreBase

MAX_CHANGE_ORDER_EVIDENCE_FILES = 20
MAX_CHANGE_ORDER_EVIDENCE_BYTES = 75_000_000


class ChangeOrderEvidenceStoreMixin(StoreBase):
    def add_change_order_evidence(
        self,
        change_order_id: str,
        *,
        original_name: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        actor: str,
    ) -> ChangeOrderEvidenceSummary | None:
        evidence_id = str(uuid4())
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
                raise ValueError("Evidence cannot be added to a locked revision")
            totals = db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(change_order_evidence.c.size_bytes), 0),
                ).where(change_order_evidence.c.change_order_id == change_order_id)
            ).one()
            if (
                totals[0] >= MAX_CHANGE_ORDER_EVIDENCE_FILES
                or totals[1] + size_bytes > MAX_CHANGE_ORDER_EVIDENCE_BYTES
            ):
                raise ValueError("Change order evidence quota exceeded")
            now = datetime.now(UTC)
            db.execute(
                change_order_evidence.insert().values(
                    id=evidence_id,
                    change_order_id=change_order_id,
                    original_name=original_name,
                    storage_key=storage_key,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    uploaded_by=actor,
                    created_at=now,
                )
            )
            self._audit(
                db,
                event="change_order.evidence_added",
                actor=actor,
                subject_type="change_order",
                subject_id=change_order_id,
                payload={"evidence_id": evidence_id, "sha256": sha256},
            )
        return ChangeOrderEvidenceSummary(
            id=evidence_id,
            change_order_id=change_order_id,
            original_name=original_name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            uploaded_by=actor,
            created_at=now,
        )

    def list_change_order_evidence(
        self, change_order_id: str
    ) -> list[ChangeOrderEvidenceSummary] | None:
        with self.engine.connect() as db:
            if not db.execute(
                select(change_orders.c.id).where(change_orders.c.id == change_order_id)
            ).first():
                return None
            rows = (
                db.execute(
                    select(change_order_evidence)
                    .where(change_order_evidence.c.change_order_id == change_order_id)
                    .order_by(change_order_evidence.c.created_at)
                )
                .mappings()
                .all()
            )
        return [ChangeOrderEvidenceSummary.model_validate(row) for row in rows]

    def get_change_order_evidence(
        self, change_order_id: str, evidence_id: str
    ) -> dict[str, Any] | None:
        with self.engine.connect() as db:
            row = (
                db.execute(
                    select(change_order_evidence).where(
                        change_order_evidence.c.id == evidence_id,
                        change_order_evidence.c.change_order_id == change_order_id,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None
