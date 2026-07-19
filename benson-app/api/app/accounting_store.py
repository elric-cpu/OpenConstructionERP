import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.engine import Connection

from .change_order_schema import change_orders
from .finance_domain import JournalEntryCreate
from .finance_journal_accounts import ensure_default_accounts
from .finance_quickbooks_outbox import canonical_json
from .finance_schema import (
    accounting_conflicts,
    invoices,
    journal_entries,
    journal_lines,
    ledger_accounts,
    payments,
    quickbooks_external_ids,
    quickbooks_outbox,
    reconciliation_items,
)
from .storage_schema import jobs
from .store_base import StoreBase


finance_write_lock = RLock()


class AccountingConflictStaleWrite(ValueError):
    pass


def post_journal(
    db: Connection,
    *,
    idempotency_key: str,
    source_type: str,
    source_id: str,
    description: str,
    occurred_at: datetime,
    actor: str,
    lines: Iterable[dict[str, Any]],
    reverses_entry_id: str | None = None,
) -> tuple[str, bool]:
    prepared = list(lines)
    debit_total = sum(int(line.get("debit_cents", 0)) for line in prepared)
    credit_total = sum(int(line.get("credit_cents", 0)) for line in prepared)
    if not prepared or debit_total <= 0 or debit_total != credit_total:
        raise ValueError("Journal entry must contain balanced non-zero lines")
    for line in prepared:
        debit = int(line.get("debit_cents", 0))
        credit = int(line.get("credit_cents", 0))
        if (debit > 0) == (credit > 0):
            raise ValueError("Each journal line must use exactly one side")
    existing = (
        db.execute(
            select(journal_entries).where(
                journal_entries.c.idempotency_key == idempotency_key
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["source_type"] != source_type or existing["source_id"] != source_id:
            raise ValueError("Journal idempotency key was reused for another source")
        return str(existing["id"]), False
    ensure_default_accounts(db)
    entry_id = str(uuid4())
    now = datetime.now(UTC)
    db.execute(
        journal_entries.insert().values(
            id=entry_id,
            idempotency_key=idempotency_key,
            source_type=source_type,
            source_id=source_id,
            description=description,
            occurred_at=occurred_at,
            posted_by=actor,
            reverses_entry_id=reverses_entry_id,
            created_at=now,
        )
    )
    db.execute(
        journal_lines.insert(),
        [
            {
                "id": str(uuid4()),
                "journal_entry_id": entry_id,
                "position": position,
                "account_code": line["account_code"],
                "debit_cents": int(line.get("debit_cents", 0)),
                "credit_cents": int(line.get("credit_cents", 0)),
                "job_id": line.get("job_id"),
                "customer_id": line.get("customer_id"),
                "invoice_id": line.get("invoice_id"),
            }
            for position, line in enumerate(prepared, start=1)
        ],
    )
    return entry_id, True


def reverse_journal(
    db: Connection,
    *,
    original_idempotency_key: str,
    reversal_idempotency_key: str,
    source_type: str,
    source_id: str,
    description: str,
    actor: str,
) -> tuple[str, bool]:
    original = (
        db.execute(
            select(journal_entries).where(
                journal_entries.c.idempotency_key == original_idempotency_key
            )
        )
        .mappings()
        .one()
    )
    rows = (
        db.execute(
            select(journal_lines).where(
                journal_lines.c.journal_entry_id == original["id"]
            )
        )
        .mappings()
        .all()
    )
    return post_journal(
        db,
        idempotency_key=reversal_idempotency_key,
        source_type=source_type,
        source_id=source_id,
        description=description,
        occurred_at=datetime.now(UTC),
        actor=actor,
        reverses_entry_id=str(original["id"]),
        lines=[
            {
                "account_code": row["account_code"],
                "debit_cents": row["credit_cents"],
                "credit_cents": row["debit_cents"],
                "job_id": row["job_id"],
                "customer_id": row["customer_id"],
                "invoice_id": row["invoice_id"],
            }
            for row in rows
        ],
    )


class AccountingStoreMixin(StoreBase):
    def post_journal_entry(
        self, entry: JournalEntryCreate, *, actor: str
    ) -> tuple[str, bool]:
        with finance_write_lock, self.engine.begin() as db:
            entry_id, created = post_journal(
                db,
                idempotency_key=entry.idempotency_key,
                source_type=entry.source_type,
                source_id=entry.source_id,
                description=entry.description,
                occurred_at=entry.occurred_at,
                actor=actor,
                lines=[line.model_dump(mode="json") for line in entry.lines],
            )
            if created:
                self._audit(
                    db,
                    event="accounting.journal_posted",
                    actor=actor,
                    subject_type="journal_entry",
                    subject_id=entry_id,
                    payload={
                        "source_type": entry.source_type,
                        "source_id": entry.source_id,
                        "line_count": len(entry.lines),
                    },
                )
        return entry_id, created

    def post_approved_adjustment(
        self,
        entry: JournalEntryCreate,
        *,
        actor: str,
        approved_by: str,
        approval_note: str,
    ) -> tuple[str, bool]:
        if entry.source_type != "adjustment":
            raise ValueError("Accounting adjustments must use the adjustment source")
        if not approved_by.strip() or not approval_note.strip():
            raise ValueError("Accounting adjustments require documented approval")
        with finance_write_lock, self.engine.begin() as db:
            entry_id, created = post_journal(
                db,
                idempotency_key=entry.idempotency_key,
                source_type=entry.source_type,
                source_id=entry.source_id,
                description=entry.description,
                occurred_at=entry.occurred_at,
                actor=actor,
                lines=[line.model_dump(mode="json") for line in entry.lines],
            )
            if created:
                self._audit(
                    db,
                    event="accounting.adjustment_posted",
                    actor=actor,
                    subject_type="journal_entry",
                    subject_id=entry_id,
                    payload={
                        "approved_by": approved_by,
                        "approval_note": approval_note,
                        "debit_cents": sum(x.debit_cents for x in entry.lines),
                        "credit_cents": sum(x.credit_cents for x in entry.lines),
                    },
                )
        return entry_id, created

    def acknowledge_quickbooks(
        self,
        outbox_id: str,
        *,
        external_id: str,
        external_version: str | None,
        acknowledged_payload: dict[str, Any],
        actor: str,
    ) -> bool:
        with finance_write_lock, self.engine.begin() as db:
            item = (
                db.execute(
                    select(quickbooks_outbox).where(quickbooks_outbox.c.id == outbox_id)
                )
                .mappings()
                .first()
            )
            if not item:
                return False
            expected = json.loads(item["payload"])
            expected_total = expected.get("total_cents")
            actual_total = acknowledged_payload.get("total_cents")
            if expected_total is not None and expected_total != actual_total:
                self._create_conflict(
                    db,
                    outbox_id=outbox_id,
                    entity_type=item["entity_type"],
                    entity_id=item["entity_id"],
                    conflict_type="total_mismatch",
                    expected_payload=expected,
                    actual_payload=acknowledged_payload,
                )
                db.execute(
                    update(quickbooks_outbox)
                    .where(quickbooks_outbox.c.id == outbox_id)
                    .values(status="conflict", updated_at=datetime.now(UTC))
                )
                return False
            external = (
                db.execute(
                    select(quickbooks_external_ids).where(
                        quickbooks_external_ids.c.entity_type == item["entity_type"],
                        quickbooks_external_ids.c.entity_id == item["entity_id"],
                    )
                )
                .mappings()
                .first()
            )
            now = datetime.now(UTC)
            if external:
                db.execute(
                    update(quickbooks_external_ids)
                    .where(quickbooks_external_ids.c.id == external["id"])
                    .values(
                        external_id=external_id,
                        external_version=external_version,
                        updated_at=now,
                    )
                )
            else:
                db.execute(
                    quickbooks_external_ids.insert().values(
                        id=str(uuid4()),
                        entity_type=item["entity_type"],
                        entity_id=item["entity_id"],
                        external_id=external_id,
                        external_version=external_version,
                        updated_at=now,
                    )
                )
            db.execute(
                update(quickbooks_outbox)
                .where(quickbooks_outbox.c.id == outbox_id)
                .values(status="acknowledged", updated_at=now)
            )
            self._audit(
                db,
                event="accounting.quickbooks_acknowledged",
                actor=actor,
                subject_type=item["entity_type"],
                subject_id=item["entity_id"],
                payload={"outbox_id": outbox_id, "external_id": external_id},
            )
        return True

    def resolve_accounting_conflict(
        self,
        conflict_id: str,
        *,
        expected_version: int,
        status: str,
        note: str,
        actor: str,
    ) -> bool:
        if status not in {"resolved", "dismissed"} or not note.strip():
            raise ValueError("Conflict resolution requires a final status and note")
        with finance_write_lock, self.engine.begin() as db:
            changed = db.execute(
                update(accounting_conflicts)
                .where(
                    accounting_conflicts.c.id == conflict_id,
                    accounting_conflicts.c.status == "open",
                    accounting_conflicts.c.version == expected_version,
                )
                .values(
                    status=status,
                    version=expected_version + 1,
                    resolved_at=datetime.now(UTC),
                    resolved_by=actor,
                    resolution_note=note.strip(),
                )
            )
            if changed.rowcount != 1:
                exists = db.execute(
                    select(accounting_conflicts.c.id).where(
                        accounting_conflicts.c.id == conflict_id
                    )
                ).first()
                if exists:
                    raise AccountingConflictStaleWrite(
                        "Accounting conflict changed; reload before retrying"
                    )
                return False
        return True

    def trial_balance(self) -> list[dict[str, Any]]:
        statement = (
            select(
                ledger_accounts.c.code,
                ledger_accounts.c.name,
                func.coalesce(func.sum(journal_lines.c.debit_cents), 0).label(
                    "debit_cents"
                ),
                func.coalesce(func.sum(journal_lines.c.credit_cents), 0).label(
                    "credit_cents"
                ),
            )
            .select_from(
                ledger_accounts.outerjoin(
                    journal_lines,
                    ledger_accounts.c.code == journal_lines.c.account_code,
                )
            )
            .group_by(ledger_accounts.c.code, ledger_accounts.c.name)
            .order_by(ledger_accounts.c.code)
        )
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(statement).mappings()]

    def ar_aging(self, *, as_of: date) -> dict[str, int]:
        buckets = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "over_90": 0}
        with self.engine.connect() as db:
            rows = db.execute(
                select(invoices.c.due_date, invoices.c.open_balance_cents).where(
                    invoices.c.status == "approved",
                    invoices.c.open_balance_cents > 0,
                )
            ).mappings()
            for row in rows:
                age = (as_of - row["due_date"]).days
                key = (
                    "current"
                    if age <= 0
                    else "1_30"
                    if age <= 30
                    else "31_60"
                    if age <= 60
                    else "61_90"
                    if age <= 90
                    else "over_90"
                )
                buckets[key] += row["open_balance_cents"]
        return buckets

    def finance_reports(self) -> dict[str, list[dict[str, Any]]]:
        with self.engine.connect() as db:
            invoice_register = [
                dict(row)
                for row in db.execute(
                    select(
                        invoices.c.number,
                        invoices.c.job_id,
                        invoices.c.kind,
                        invoices.c.status,
                        invoices.c.issue_date,
                        invoices.c.subtotal_cents,
                        invoices.c.total_cents,
                        invoices.c.open_balance_cents,
                    ).order_by(invoices.c.issue_date, invoices.c.number)
                ).mappings()
            ]
            cash_receipts = [
                dict(row)
                for row in db.execute(
                    select(
                        payments.c.provider_payment_id,
                        payments.c.invoice_id,
                        payments.c.status,
                        payments.c.amount_cents,
                        payments.c.fee_cents,
                        payments.c.settled_at,
                    ).where(payments.c.status.in_(("settled", "refunded", "disputed")))
                ).mappings()
            ]
            retainage = [
                dict(row)
                for row in db.execute(
                    select(
                        invoices.c.job_id,
                        func.sum(invoices.c.retainage_cents).label("held_cents"),
                        func.sum(invoices.c.retainage_release_cents).label(
                            "released_cents"
                        ),
                    )
                    .where(invoices.c.status == "approved")
                    .group_by(invoices.c.job_id)
                ).mappings()
            ]
            wip = [
                dict(row)
                for row in db.execute(
                    select(
                        jobs.c.id.label("job_id"),
                        jobs.c.contract_value_cents,
                        func.coalesce(func.sum(invoices.c.subtotal_cents), 0).label(
                            "billed_cents"
                        ),
                    )
                    .select_from(
                        jobs.outerjoin(
                            invoices,
                            (invoices.c.job_id == jobs.c.id)
                            & (invoices.c.status == "approved"),
                        )
                    )
                    .group_by(jobs.c.id, jobs.c.contract_value_cents)
                ).mappings()
            ]
            change_order_exposure = [
                dict(row)
                for row in db.execute(
                    select(
                        change_orders.c.job_id,
                        change_orders.c.status,
                        func.sum(change_orders.c.subtotal_cents).label("amount_cents"),
                    )
                    .where(
                        change_orders.c.status.in_(("draft", "submitted", "approved"))
                    )
                    .group_by(change_orders.c.job_id, change_orders.c.status)
                ).mappings()
            ]
            reconciliation = [
                dict(row)
                for row in db.execute(
                    select(reconciliation_items).order_by(
                        reconciliation_items.c.occurred_at.desc()
                    )
                ).mappings()
            ]
            profitability = [
                dict(row)
                for row in db.execute(
                    select(
                        journal_lines.c.job_id,
                        func.sum(
                            case(
                                (
                                    ledger_accounts.c.account_type == "revenue",
                                    journal_lines.c.credit_cents
                                    - journal_lines.c.debit_cents,
                                ),
                                else_=0,
                            )
                        ).label("revenue_cents"),
                        func.sum(
                            case(
                                (
                                    ledger_accounts.c.account_type == "expense",
                                    journal_lines.c.debit_cents
                                    - journal_lines.c.credit_cents,
                                ),
                                else_=0,
                            )
                        ).label("cost_cents"),
                    )
                    .join(
                        ledger_accounts,
                        ledger_accounts.c.code == journal_lines.c.account_code,
                    )
                    .where(journal_lines.c.job_id.is_not(None))
                    .group_by(journal_lines.c.job_id)
                ).mappings()
            ]
        return {
            "invoice_register": invoice_register,
            "cash_receipts": cash_receipts,
            "retainage": retainage,
            "wip": wip,
            "change_order_exposure": change_order_exposure,
            "reconciliation": reconciliation,
            "job_profitability": profitability,
        }

    def _create_conflict(
        self,
        db: Connection,
        *,
        outbox_id: str | None,
        entity_type: str,
        entity_id: str,
        conflict_type: str,
        expected_payload: dict[str, Any],
        actual_payload: dict[str, Any],
    ) -> str:
        conflict_id = str(uuid4())
        db.execute(
            accounting_conflicts.insert().values(
                id=conflict_id,
                outbox_id=outbox_id,
                entity_type=entity_type,
                entity_id=entity_id,
                conflict_type=conflict_type,
                expected_payload=canonical_json(expected_payload),
                actual_payload=canonical_json(actual_payload),
                status="open",
                version=1,
                created_at=datetime.now(UTC),
                resolved_at=None,
                resolved_by=None,
                resolution_note=None,
            )
        )
        return conflict_id
