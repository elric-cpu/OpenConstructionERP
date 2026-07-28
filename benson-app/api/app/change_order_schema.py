from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from .storage_schema import metadata

change_orders = Table(
    "change_orders",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("root_id", String(36), nullable=False, index=True),
    Column("previous_revision_id", String(36), ForeignKey("change_orders.id")),
    Column("revision", Integer, nullable=False),
    Column("number", String(60), nullable=False, unique=True),
    Column("job_id", String(36), ForeignKey("jobs.id"), nullable=False, index=True),
    Column("estimate_id", String(36), ForeignKey("estimates.id"), nullable=False),
    Column("customer_id", String(36), ForeignKey("customers.id"), nullable=False),
    Column("originating_field_report_id", String(36), ForeignKey("field_reports.id")),
    Column("status", String(40), nullable=False),
    Column("version", Integer, nullable=False),
    Column("title", String(300), nullable=False),
    Column("schedule_impact_days", Integer, nullable=False),
    Column("internal_notes", Text, nullable=False),
    Column("customer_explanation", Text, nullable=False),
    Column("subtotal_cents", BigInteger, nullable=False),
    Column("created_by", String(320), nullable=False),
    Column("submitted_by", String(320)),
    Column("submitted_at", DateTime(timezone=True)),
    Column("decided_by", String(320)),
    Column("decided_at", DateTime(timezone=True)),
    Column("decision_note", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("root_id", "revision", name="uq_change_order_revision"),
    CheckConstraint("revision > 0", name="ck_change_orders_revision"),
    CheckConstraint("version > 0", name="ck_change_orders_version"),
    CheckConstraint("subtotal_cents >= 0", name="ck_change_orders_subtotal"),
    CheckConstraint(
        "status IN ('draft', 'submitted', 'approved', 'rejected', 'void')",
        name="ck_change_orders_status",
    ),
)

change_order_lines = Table(
    "change_order_lines",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "change_order_id",
        String(36),
        ForeignKey("change_orders.id"),
        nullable=False,
        index=True,
    ),
    Column("position", Integer, nullable=False),
    Column("description", String(1_000), nullable=False),
    Column("quantity", String(40), nullable=False),
    Column("unit", String(40), nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
    Column("line_total_cents", BigInteger, nullable=False),
    UniqueConstraint(
        "change_order_id", "position", name="uq_change_order_line_position"
    ),
)

change_order_evidence = Table(
    "change_order_evidence",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "change_order_id",
        String(36),
        ForeignKey("change_orders.id"),
        nullable=False,
        index=True,
    ),
    Column("original_name", String(500), nullable=False),
    Column("storage_key", String(1_000), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("uploaded_by", String(320), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

change_order_approvals = Table(
    "change_order_approvals",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "change_order_id",
        String(36),
        ForeignKey("change_orders.id"),
        nullable=False,
        unique=True,
    ),
    Column("decision", String(20), nullable=False),
    Column("note", Text, nullable=False),
    Column("actor", String(320), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "decision IN ('approved', 'rejected')", name="ck_change_order_decision"
    ),
)
