"""durable_outbox

Revision ID: 9b56c7a4e210
Revises: 0d12a9d31f3c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9b56c7a4e210"
down_revision: str | None = "0d12a9d31f3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = sa.Enum(
        "PENDING",
        "LEASED",
        "PROCESSING",
        "RETRY",
        "PUBLISHED",
        "DEAD_LETTER",
        name="outboxstatus",
    )
    status.create(op.get_bind())
    op.add_column(
        "outbox_events",
        sa.Column(
            "status",
            status,
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "outbox_events",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "outbox_events",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column("outbox_events", sa.Column("lease_owner", sa.String(length=200)))
    op.add_column("outbox_events", sa.Column("lease_until", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("dispatched_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("dead_letter_at", sa.DateTime(timezone=True)))
    op.add_column("outbox_events", sa.Column("last_error", sa.Text()))
    op.alter_column("outbox_events", "status", server_default=None)
    op.alter_column("outbox_events", "attempt_count", server_default=None)
    op.drop_constraint(
        "outbox_events_idempotency_key_key",
        "outbox_events",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_outbox_tenant_idempotency",
        "outbox_events",
        ["tenant_id", "idempotency_key"],
    )
    op.create_index(
        "ix_outbox_dispatch_ready",
        "outbox_events",
        ["tenant_id", "status", "next_attempt_at", "lease_until"],
    )
    op.create_table(
        "inbox_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("handler_name", sa.String(length=200), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "event_id",
            "handler_name",
            name="uq_inbox_tenant_event_handler",
        ),
    )
    op.create_index("ix_inbox_receipts_tenant_id", "inbox_receipts", ["tenant_id"])
    op.create_index("ix_inbox_receipts_event_id", "inbox_receipts", ["event_id"])
    op.execute('ALTER TABLE "inbox_receipts" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "inbox_receipts" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON "inbox_receipts"
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "inbox_receipts"')
    op.execute('ALTER TABLE "inbox_receipts" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_inbox_receipts_event_id", table_name="inbox_receipts")
    op.drop_index("ix_inbox_receipts_tenant_id", table_name="inbox_receipts")
    op.drop_table("inbox_receipts")
    op.drop_index("ix_outbox_dispatch_ready", table_name="outbox_events")
    op.drop_constraint(
        "uq_outbox_tenant_idempotency",
        "outbox_events",
        type_="unique",
    )
    op.create_unique_constraint(
        "outbox_events_idempotency_key_key",
        "outbox_events",
        ["idempotency_key"],
    )
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "dead_letter_at")
    op.drop_column("outbox_events", "dispatched_at")
    op.drop_column("outbox_events", "lease_until")
    op.drop_column("outbox_events", "lease_owner")
    op.drop_column("outbox_events", "next_attempt_at")
    op.drop_column("outbox_events", "attempt_count")
    op.drop_column("outbox_events", "status")
    op.execute("DROP TYPE outboxstatus")
