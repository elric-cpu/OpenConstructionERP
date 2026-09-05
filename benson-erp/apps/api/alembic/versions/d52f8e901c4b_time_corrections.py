"""time_corrections

Revision ID: d52f8e901c4b
Revises: b510e1f46a72
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d52f8e901c4b"
down_revision: str | None = "b510e1f46a72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    correction_status = postgresql.ENUM(
        "PENDING_RECERTIFICATION",
        "PENDING_APPROVAL",
        "COMPLETED",
        name="timecorrectionstatus",
        create_type=False,
    )
    correction_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "time_corrections",
        sa.Column("original_entry_id", sa.Uuid(), nullable=False),
        sa.Column("replacement_entry_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", correction_status, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "original_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "replacement_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "original_entry_id"),
        sa.UniqueConstraint("tenant_id", "replacement_entry_id"),
    )
    op.create_index("ix_time_corrections_tenant_id", "time_corrections", ["tenant_id"])
    op.create_index(
        "ix_time_correction_tenant_status",
        "time_corrections",
        ["tenant_id", "status"],
    )
    op.execute('ALTER TABLE "time_corrections" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "time_corrections" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON "time_corrections"
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "time_corrections"')
    op.execute('ALTER TABLE "time_corrections" DISABLE ROW LEVEL SECURITY')
    op.drop_table("time_corrections")
    op.execute("DROP TYPE timecorrectionstatus")
