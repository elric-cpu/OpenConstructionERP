"""people_identity

Revision ID: c4a1e62f7d90
Revises: 9b56c7a4e210
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4a1e62f7d90"
down_revision: str | None = "9b56c7a4e210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    employee_status = postgresql.ENUM(
        "DRAFT",
        "IDENTITY_REQUESTED",
        "IDENTITY_CREATED",
        "ACTIVE",
        "INACTIVE",
        name="employeestatus",
        create_type=False,
    )
    provisioning_status = postgresql.ENUM(
        "PENDING",
        "CREATED",
        name="identityprovisioningstatus",
        create_type=False,
    )
    employee_status.create(op.get_bind(), checkfirst=True)
    provisioning_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "organizations",
        sa.Column("google_identity_domain", sa.String(length=253)),
    )
    op.add_column(
        "organizations",
        sa.Column("google_customer_id", sa.String(length=100)),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "google_default_org_unit_path",
            sa.String(length=500),
            server_default="/",
            nullable=False,
        ),
    )
    op.alter_column("organizations", "google_default_org_unit_path", server_default=None)
    op.create_table(
        "employees",
        sa.Column("employee_number", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("preferred_name", sa.String(length=100)),
        sa.Column("personal_email", sa.String(length=320), nullable=False),
        sa.Column("company_username", sa.String(length=80), nullable=False),
        sa.Column("company_email", sa.String(length=320)),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("manager_user_id", sa.Uuid()),
        sa.Column("status", employee_status, nullable=False),
        sa.Column("google_subject_id", sa.String(length=100)),
        sa.Column("google_org_unit_path", sa.String(length=500)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.Uuid()),
        sa.Column("identity_created_at", sa.DateTime(timezone=True)),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "employee_number"),
        sa.UniqueConstraint("tenant_id", "company_username"),
        sa.UniqueConstraint("tenant_id", "company_email"),
    )
    op.create_index("ix_employees_tenant_id", "employees", ["tenant_id"])
    op.create_table(
        "identity_provisioning_requests",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("status", provisioning_status, nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("primary_email", sa.String(length=320), nullable=False),
        sa.Column("external_user_id", sa.String(length=100)),
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
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "employee_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_index(
        "ix_identity_provisioning_requests_tenant_id",
        "identity_provisioning_requests",
        ["tenant_id"],
    )
    op.create_index(
        "ix_identity_requests_tenant_status",
        "identity_provisioning_requests",
        ["tenant_id", "status"],
    )
    for table in ("employees", "identity_provisioning_requests"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"""CREATE POLICY tenant_isolation ON "{table}"
            USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
        )


def downgrade() -> None:
    for table in ("identity_provisioning_requests", "employees"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    op.drop_index(
        "ix_identity_requests_tenant_status",
        table_name="identity_provisioning_requests",
    )
    op.drop_index(
        "ix_identity_provisioning_requests_tenant_id",
        table_name="identity_provisioning_requests",
    )
    op.drop_table("identity_provisioning_requests")
    op.drop_index("ix_employees_tenant_id", table_name="employees")
    op.drop_table("employees")
    op.drop_column("organizations", "google_default_org_unit_path")
    op.drop_column("organizations", "google_customer_id")
    op.drop_column("organizations", "google_identity_domain")
    op.execute("DROP TYPE identityprovisioningstatus")
    op.execute("DROP TYPE employeestatus")
