import importlib
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

import app.finance_domain as finance_domain
from app.accounting_store import post_journal, reverse_journal
from app.config import Settings
from app.finance_journal_accounts import DEFAULT_ACCOUNTS
from app.finance_accounting_outbox import canonical_json, enqueue_accounting_export
from app.finance_schema import journal_entries, journal_lines, ledger_accounts
from app.storage import operations_store


def test_invoice_and_journal_models_enforce_accounting_invariants() -> None:
    domain = importlib.reload(finance_domain)
    source_id = uuid4()
    line = domain.InvoiceLineInput(
        description="Framing progress",
        quantity=Decimal("1.25"),
        unit="lot",
        unit_price_cents=101,
        source_type="estimate",
        source_id=source_id,
    )
    assert line.total_cents() == 126
    invoice = domain.InvoiceCreate(
        job_id=uuid4(),
        kind=domain.InvoiceKind.PROGRESS,
        issue_date=date(2026, 7, 19),
        due_date=date(2026, 8, 18),
        retainage_cents=12,
        lines=[line],
    )
    assert invoice.kind is domain.InvoiceKind.PROGRESS

    invalid_invoices = (
        {"due_date": date(2026, 7, 18)},
        {"retainage_cents": 127},
        {"kind": domain.InvoiceKind.DEPOSIT, "retainage_cents": 1},
    )
    for overrides in invalid_invoices:
        with pytest.raises(ValidationError):
            domain.InvoiceCreate(
                job_id=uuid4(),
                kind=overrides.get("kind", domain.InvoiceKind.PROGRESS),
                issue_date=date(2026, 7, 19),
                due_date=overrides.get("due_date", date(2026, 8, 18)),
                retainage_cents=overrides.get("retainage_cents", 0),
                lines=[line],
            )

    debit = domain.JournalLineInput(account_code="1100", debit_cents=126)
    credit = domain.JournalLineInput(account_code="4000", credit_cents=126)
    entry = domain.JournalEntryCreate(
        idempotency_key="finance-domain-entry-1",
        source_type="invoice",
        source_id=str(uuid4()),
        description="Post progress billing",
        occurred_at=datetime.now(UTC),
        lines=[debit, credit],
    )
    assert sum(item.debit_cents for item in entry.lines) == 126
    with pytest.raises(ValidationError):
        domain.JournalLineInput(account_code="1100")
    with pytest.raises(ValidationError):
        domain.JournalLineInput(account_code="1100", debit_cents=1, credit_cents=1)
    with pytest.raises(ValidationError):
        domain.JournalEntryCreate(
            idempotency_key="finance-domain-entry-2",
            source_type="invoice",
            source_id=str(uuid4()),
            description="Unbalanced",
            occurred_at=datetime.now(UTC),
            lines=[debit, domain.JournalLineInput(account_code="4000", credit_cents=1)],
        )


def test_journal_and_accounting_outbox_are_idempotent(
    isolated_settings: Settings,
) -> None:
    engine = operations_store(isolated_settings.resolved_database_url()).engine
    occurred_at = datetime.now(UTC)
    lines = [
        {"account_code": "1100", "debit_cents": 5000, "credit_cents": 0},
        {"account_code": "4000", "debit_cents": 0, "credit_cents": 5000},
    ]
    with engine.begin() as db:
        entry_id, created = post_journal(
            db,
            idempotency_key="invoice-post-0001",
            source_type="invoice",
            source_id="invoice-1",
            description="Invoice approved",
            occurred_at=occurred_at,
            actor="books@example.com",
            lines=lines,
        )
        duplicate_id, duplicate_created = post_journal(
            db,
            idempotency_key="invoice-post-0001",
            source_type="invoice",
            source_id="invoice-1",
            description="Invoice approved",
            occurred_at=occurred_at,
            actor="books@example.com",
            lines=lines,
        )
        assert (duplicate_id, duplicate_created) == (entry_id, False)
        with pytest.raises(ValueError, match="another source"):
            post_journal(
                db,
                idempotency_key="invoice-post-0001",
                source_type="payment",
                source_id="payment-1",
                description="Invalid reuse",
                occurred_at=occurred_at,
                actor="books@example.com",
                lines=lines,
            )
        reversal_id, reversal_created = reverse_journal(
            db,
            original_idempotency_key="invoice-post-0001",
            reversal_idempotency_key="invoice-reverse-0001",
            source_type="invoice_void",
            source_id="invoice-1",
            description="Void invoice",
            actor="books@example.com",
        )
        assert reversal_created is True
        assert reversal_id != entry_id

        payload = {"total_cents": 5000, "invoice": "BHS-2026-0001"}
        outbox_id, outbox_created = enqueue_accounting_export(
            db,
            entity_type="invoice",
            entity_id="invoice-1",
            operation="upsert",
            idempotency_key="accounting-invoice-0001",
            payload=payload,
        )
        assert outbox_created is True
        assert canonical_json(payload) == (
            '{"invoice":"BHS-2026-0001","total_cents":5000}'
        )
        assert enqueue_accounting_export(
            db,
            entity_type="invoice",
            entity_id="invoice-1",
            operation="upsert",
            idempotency_key="accounting-invoice-0001",
            payload=payload,
        ) == (outbox_id, False)
        with pytest.raises(ValueError, match="payload mismatch"):
            enqueue_accounting_export(
                db,
                entity_type="invoice",
                entity_id="invoice-1",
                operation="upsert",
                idempotency_key="accounting-invoice-0001",
                payload={"total_cents": 4999},
            )

    with engine.connect() as db:
        assert set(db.execute(select(ledger_accounts.c.code)).scalars()) == set(
            DEFAULT_ACCOUNTS
        )
        assert (
            db.execute(select(func.count()).select_from(journal_entries)).scalar_one()
            == 2
        )
        assert (
            db.execute(select(func.count()).select_from(journal_lines)).scalar_one()
            == 4
        )
