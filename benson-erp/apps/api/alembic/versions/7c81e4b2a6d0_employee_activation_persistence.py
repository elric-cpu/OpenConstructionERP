"""employee_activation_persistence

Revision ID: 7c81e4b2a6d0
Revises: 1a2c9d8e4f60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c81e4b2a6d0"
down_revision: str | None = "1a2c9d8e4f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("activation_sent_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "employees",
        sa.Column("erp_access_confirmed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "employee_activation_requests",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_delivery_secret", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
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
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.alter_column(
        "employee_activation_requests",
        "attempt_count",
        server_default=None,
    )
    op.create_index(
        "ix_employee_activation_requests_tenant_id",
        "employee_activation_requests",
        ["tenant_id"],
    )
    op.create_index(
        "ix_employee_activation_active",
        "employee_activation_requests",
        ["tenant_id", "employee_id", "expires_at"],
    )
    op.execute('ALTER TABLE "employee_activation_requests" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "employee_activation_requests" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON "employee_activation_requests"
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS tenant_isolation ON "employee_activation_requests"'
    )
    op.execute('ALTER TABLE "employee_activation_requests" DISABLE ROW LEVEL SECURITY')
    op.drop_index(
        "ix_employee_activation_active",
        table_name="employee_activation_requests",
    )
    op.drop_index(
        "ix_employee_activation_requests_tenant_id",
        table_name="employee_activation_requests",
    )
    op.drop_table("employee_activation_requests")
    op.drop_column("employees", "erp_access_confirmed_at")
    op.drop_column("employees", "activation_sent_at")
