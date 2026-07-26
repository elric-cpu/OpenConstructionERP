"""native_scheduling

Revision ID: 74a31d0cd3af
Revises: c4a1e62f7d90
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "74a31d0cd3af"
down_revision: str | None = "c4a1e62f7d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def tenant_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    activity_status = postgresql.ENUM(
        "PLANNED",
        "CONFIRMED",
        "IN_PROGRESS",
        "COMPLETE",
        "CANCELLED",
        name="activitystatus",
        create_type=False,
    )
    activity_status.create(op.get_bind(), checkfirst=True)
    op.add_column("employees", sa.Column("user_id", sa.Uuid()))
    op.create_unique_constraint(
        "uq_employees_tenant_user_id",
        "employees",
        ["tenant_id", "user_id"],
    )
    op.create_unique_constraint(
        "uq_projects_tenant_id_id",
        "projects",
        ["tenant_id", "id"],
    )
    op.create_table(
        "schedules",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        *tenant_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "project_id"),
    )
    op.create_index("ix_schedules_tenant_id", "schedules", ["tenant_id"])
    op.create_table(
        "schedule_activities",
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", activity_status, nullable=False),
        sa.Column("location", sa.String(length=500)),
        sa.Column("required_tools", sa.Text()),
        *tenant_columns(),
        sa.CheckConstraint(
            "end_at > start_at",
            name="ck_schedule_activity_positive_duration",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["schedules.tenant_id", "schedules.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_index(
        "ix_schedule_activity_tenant_window",
        "schedule_activities",
        ["tenant_id", "start_at", "end_at"],
    )
    op.create_index(
        "ix_schedule_activities_tenant_id",
        "schedule_activities",
        ["tenant_id"],
    )
    op.create_table(
        "schedule_assignments",
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_role", sa.String(length=100)),
        *tenant_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "activity_id"],
            ["schedule_activities.tenant_id", "schedule_activities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "activity_id", "employee_id"),
    )
    op.create_index(
        "ix_schedule_assignment_tenant_employee",
        "schedule_assignments",
        ["tenant_id", "employee_id"],
    )
    op.create_index(
        "ix_schedule_assignments_tenant_id",
        "schedule_assignments",
        ["tenant_id"],
    )
    for table in ("schedules", "schedule_activities", "schedule_assignments"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"""CREATE POLICY tenant_isolation ON "{table}"
            USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
        )


def downgrade() -> None:
    for table in ("schedule_assignments", "schedule_activities", "schedules"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    op.drop_table("schedule_assignments")
    op.drop_table("schedule_activities")
    op.drop_table("schedules")
    op.drop_constraint("uq_projects_tenant_id_id", "projects", type_="unique")
    op.drop_constraint("uq_employees_tenant_user_id", "employees", type_="unique")
    op.drop_column("employees", "user_id")
    op.execute("DROP TYPE activitystatus")
