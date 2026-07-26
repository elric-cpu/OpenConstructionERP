"""daily_timekeeping

Revision ID: b510e1f46a72
Revises: 74a31d0cd3af
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b510e1f46a72"
down_revision: str | None = "74a31d0cd3af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    time_entry_status = postgresql.ENUM(
        "DRAFT",
        "CERTIFIED",
        "APPROVED",
        "CORRECTED",
        name="timeentrystatus",
        create_type=False,
    )
    time_entry_source = postgresql.ENUM(
        "WEB",
        "OFFLINE",
        "CREW",
        name="timeentrysource",
        create_type=False,
    )
    time_entry_status.create(op.get_bind(), checkfirst=True)
    time_entry_source.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "time_entries",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("total_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("regular_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("double_time_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("travel_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("leave_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("indirect_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("uncompensated_overtime_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("schedule_assignment_id", sa.Uuid()),
        sa.Column("contract_code", sa.String(length=100)),
        sa.Column("task_order", sa.String(length=100)),
        sa.Column("clin", sa.String(length=100)),
        sa.Column("funding_line", sa.String(length=100)),
        sa.Column("charge_code", sa.String(length=100), nullable=False),
        sa.Column("cost_code", sa.String(length=100)),
        sa.Column("labor_category", sa.String(length=100)),
        sa.Column("work_classification", sa.String(length=150)),
        sa.Column("wage_determination", sa.String(length=150)),
        sa.Column("trade", sa.String(length=100)),
        sa.Column("location", sa.String(length=500)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("late_reason", sa.Text()),
        sa.Column("status", time_entry_status, nullable=False),
        sa.Column("source", time_entry_source, nullable=False),
        sa.Column("client_operation_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(length=200)),
        sa.Column("original_device_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "server_received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.Column("certified_by", sa.Uuid()),
        sa.Column("certification_statement", sa.Text()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.Uuid()),
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
        sa.CheckConstraint("end_at > start_at", name="ck_time_entry_positive_duration"),
        sa.CheckConstraint("break_minutes >= 0", name="ck_time_entry_break_nonnegative"),
        sa.CheckConstraint("total_hours >= 0", name="ck_time_entry_total_nonnegative"),
        sa.CheckConstraint(
            "total_hours = regular_hours + overtime_hours + double_time_hours"
            " + travel_hours + leave_hours + indirect_hours",
            name="ck_time_entry_classified_total",
        ),
        sa.CheckConstraint(
            "uncompensated_overtime_hours <= overtime_hours",
            name="ck_time_entry_uncompensated_subset",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "schedule_assignment_id"],
            ["schedule_assignments.tenant_id", "schedule_assignments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "client_operation_id"),
    )
    op.create_index("ix_time_entries_tenant_id", "time_entries", ["tenant_id"])
    op.create_index(
        "ix_time_entry_tenant_employee_date",
        "time_entries",
        ["tenant_id", "employee_id", "work_date"],
    )
    op.create_index(
        "ix_time_entry_tenant_status",
        "time_entries",
        ["tenant_id", "status"],
    )
    op.execute('ALTER TABLE "time_entries" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "time_entries" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON "time_entries"
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "time_entries"')
    op.execute('ALTER TABLE "time_entries" DISABLE ROW LEVEL SECURITY')
    op.drop_table("time_entries")
    op.execute("DROP TYPE timeentrysource")
    op.execute("DROP TYPE timeentrystatus")
