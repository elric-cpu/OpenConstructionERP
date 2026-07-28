from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from .storage_schema import metadata


invoice_number_counters = Table(
    "invoice_number_counters",
    metadata,
    Column("year", Integer, primary_key=True),
    Column("next_value", Integer, nullable=False),
    CheckConstraint("next_value > 0", name="ck_invoice_counters_next_value"),
)

invoices = Table(
    "invoices",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("number", String(40), nullable=False, unique=True),
    Column("job_id", String(36), ForeignKey("jobs.id"), nullable=False, index=True),
    Column(
        "customer_id",
        String(36),
        ForeignKey("customers.id"),
        nullable=False,
        index=True,
    ),
    Column("kind", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("version", Integer, nullable=False),
    Column("issue_date", Date, nullable=False),
    Column("due_date", Date, nullable=False, index=True),
    Column("currency", String(3), nullable=False),
    Column("memo", Text, nullable=False),
    Column("subtotal_cents", BigInteger, nullable=False),
    Column("tax_cents", BigInteger, nullable=False),
    Column("retainage_cents", BigInteger, nullable=False),
    Column("retainage_release_cents", BigInteger, nullable=False),
    Column("total_cents", BigInteger, nullable=False),
    Column("open_balance_cents", BigInteger, nullable=False),
    Column("snapshot_json", Text),
    Column("snapshot_sha256", String(64)),
    Column("created_by", String(320), nullable=False),
    Column("approved_by", String(320)),
    Column("approved_at", DateTime(timezone=True)),
    Column("voided_by", String(320)),
    Column("voided_at", DateTime(timezone=True)),
    Column("void_note", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("kind IN ('deposit', 'progress', 'final')", name="ck_invoice_kind"),
    CheckConstraint(
        "status IN ('draft', 'approved', 'void')", name="ck_invoice_status"
    ),
    CheckConstraint("version > 0", name="ck_invoice_version"),
    CheckConstraint("currency = 'USD'", name="ck_invoice_currency"),
    CheckConstraint("subtotal_cents >= 0", name="ck_invoice_subtotal"),
    CheckConstraint("tax_cents >= 0", name="ck_invoice_tax"),
    CheckConstraint("retainage_cents >= 0", name="ck_invoice_retainage"),
    CheckConstraint(
        "retainage_release_cents >= 0", name="ck_invoice_retainage_release"
    ),
    CheckConstraint("total_cents >= 0", name="ck_invoice_total"),
    CheckConstraint("due_date >= issue_date", name="ck_invoice_dates"),
)

invoice_lines = Table(
    "invoice_lines",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "invoice_id",
        String(36),
        ForeignKey("invoices.id"),
        nullable=False,
        index=True,
    ),
    Column("position", Integer, nullable=False),
    Column("description", String(1_000), nullable=False),
    Column("quantity", String(40), nullable=False),
    Column("unit", String(40), nullable=False),
    Column("unit_price_cents", BigInteger, nullable=False),
    Column("line_total_cents", BigInteger, nullable=False),
    Column("source_type", String(30), nullable=False),
    Column("source_id", String(36), nullable=False, index=True),
    UniqueConstraint("invoice_id", "position", name="uq_invoice_line_position"),
    CheckConstraint(
        "source_type IN ('estimate', 'change_order')",
        name="ck_invoice_line_source",
    ),
    CheckConstraint("line_total_cents >= 0", name="ck_invoice_line_total"),
)

invoice_credits = Table(
    "invoice_credits",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("number", String(60), nullable=False, unique=True),
    Column(
        "invoice_id",
        String(36),
        ForeignKey("invoices.id"),
        nullable=False,
        index=True,
    ),
    Column("amount_cents", BigInteger, nullable=False),
    Column("reason", Text, nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("amount_cents > 0", name="ck_invoice_credit_amount"),
)

stripe_outbox = Table(
    "stripe_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("invoice_id", String(36), ForeignKey("invoices.id"), nullable=False),
    Column("operation", String(60), nullable=False),
    Column("idempotency_key", String(200), nullable=False, unique=True),
    Column("payload", Text, nullable=False),
    Column("status", String(30), nullable=False, index=True),
    Column("attempts", Integer, nullable=False),
    Column("provider_session_id", String(200), unique=True),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')",
        name="ck_stripe_outbox_status",
    ),
)

payments = Table(
    "payments",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("invoice_id", String(36), ForeignKey("invoices.id"), nullable=False),
    Column("provider", String(30), nullable=False),
    Column("provider_payment_id", String(200), nullable=False, unique=True),
    Column("status", String(30), nullable=False),
    Column("version", Integer, nullable=False),
    Column("amount_cents", BigInteger, nullable=False),
    Column("fee_cents", BigInteger, nullable=False),
    Column("refunded_cents", BigInteger, nullable=False),
    Column("disputed_cents", BigInteger, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("settled_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'processing', 'settled', 'failed', 'refunded', 'disputed')",
        name="ck_payment_status",
    ),
    CheckConstraint("version > 0", name="ck_payment_version"),
    CheckConstraint("amount_cents >= 0", name="ck_payment_amount"),
    CheckConstraint("fee_cents >= 0", name="ck_payment_fee"),
    CheckConstraint("refunded_cents >= 0", name="ck_payment_refunded"),
    CheckConstraint("disputed_cents >= 0", name="ck_payment_disputed"),
)

payment_refunds = Table(
    "payment_refunds",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("payment_id", String(36), ForeignKey("payments.id"), nullable=False),
    Column("provider_refund_id", String(200), nullable=False, unique=True),
    Column("amount_cents", BigInteger, nullable=False),
    Column("status", String(30), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("amount_cents > 0", name="ck_payment_refund_amount"),
)

payment_disputes = Table(
    "payment_disputes",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("payment_id", String(36), ForeignKey("payments.id"), nullable=False),
    Column("provider_dispute_id", String(200), nullable=False, unique=True),
    Column("amount_cents", BigInteger, nullable=False),
    Column("status", String(30), nullable=False),
    Column("reason", String(200), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("amount_cents > 0", name="ck_payment_dispute_amount"),
)

stripe_webhook_events = Table(
    "stripe_webhook_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("provider_event_id", String(200), nullable=False, unique=True),
    Column("event_type", String(120), nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("status", String(30), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("processed_at", DateTime(timezone=True)),
    Column("last_error", Text),
)

ledger_accounts = Table(
    "ledger_accounts",
    metadata,
    Column("code", String(40), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("account_type", String(30), nullable=False),
    Column("active", Integer, nullable=False),
    CheckConstraint(
        "account_type IN ('asset', 'liability', 'equity', 'revenue', 'expense')",
        name="ck_ledger_account_type",
    ),
)

journal_entries = Table(
    "journal_entries",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("idempotency_key", String(200), nullable=False, unique=True),
    Column("source_type", String(60), nullable=False),
    Column("source_id", String(200), nullable=False),
    Column("description", String(1_000), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("posted_by", String(320), nullable=False),
    Column("reverses_entry_id", String(36), ForeignKey("journal_entries.id")),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

journal_lines = Table(
    "journal_lines",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "journal_entry_id",
        String(36),
        ForeignKey("journal_entries.id"),
        nullable=False,
        index=True,
    ),
    Column("position", Integer, nullable=False),
    Column(
        "account_code", String(40), ForeignKey("ledger_accounts.code"), nullable=False
    ),
    Column("debit_cents", BigInteger, nullable=False),
    Column("credit_cents", BigInteger, nullable=False),
    Column("job_id", String(36), ForeignKey("jobs.id")),
    Column("customer_id", String(36), ForeignKey("customers.id")),
    Column("invoice_id", String(36), ForeignKey("invoices.id")),
    UniqueConstraint("journal_entry_id", "position", name="uq_journal_line_position"),
    CheckConstraint(
        "(debit_cents > 0 AND credit_cents = 0) OR "
        "(credit_cents > 0 AND debit_cents = 0)",
        name="ck_journal_line_one_side",
    ),
)

accounting_outbox = Table(
    "accounting_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("entity_type", String(60), nullable=False),
    Column("entity_id", String(200), nullable=False),
    Column("operation", String(60), nullable=False),
    Column("idempotency_key", String(200), nullable=False, unique=True),
    Column("payload", Text, nullable=False),
    Column("status", String(30), nullable=False, index=True),
    Column("attempts", Integer, nullable=False),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'processing', 'acknowledged', 'failed', 'conflict')",
        name="ck_accounting_outbox_status",
    ),
)

accounting_external_ids = Table(
    "accounting_external_ids",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("entity_type", String(60), nullable=False),
    Column("entity_id", String(200), nullable=False),
    Column("external_id", String(200), nullable=False),
    Column("external_version", String(200)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("entity_type", "entity_id", name="uq_accounting_external_entity"),
    UniqueConstraint("entity_type", "external_id", name="uq_accounting_external_id"),
)

accounting_conflicts = Table(
    "accounting_conflicts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("outbox_id", String(36), ForeignKey("accounting_outbox.id")),
    Column("entity_type", String(60), nullable=False),
    Column("entity_id", String(200), nullable=False),
    Column("conflict_type", String(80), nullable=False),
    Column("expected_payload", Text, nullable=False),
    Column("actual_payload", Text, nullable=False),
    Column("status", String(30), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    Column("resolved_by", String(320)),
    Column("resolution_note", Text),
    CheckConstraint(
        "status IN ('open', 'resolved', 'dismissed')",
        name="ck_accounting_conflict_status",
    ),
    CheckConstraint("version > 0", name="ck_accounting_conflict_version"),
)

reconciliation_items = Table(
    "reconciliation_items",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("provider", String(30), nullable=False),
    Column("provider_transaction_id", String(200), nullable=False),
    Column("transaction_type", String(60), nullable=False),
    Column("payment_id", String(36), ForeignKey("payments.id")),
    Column("gross_cents", BigInteger, nullable=False),
    Column("fee_cents", BigInteger, nullable=False),
    Column("net_cents", BigInteger, nullable=False),
    Column("status", String(30), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "provider", "provider_transaction_id", name="uq_reconciliation_provider_tx"
    ),
    CheckConstraint(
        "status IN ('matched', 'unmatched', 'adjusted')",
        name="ck_reconciliation_status",
    ),
)
