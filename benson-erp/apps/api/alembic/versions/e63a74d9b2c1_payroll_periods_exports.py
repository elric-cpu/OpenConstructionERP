"""payroll_periods_exports

Revision ID: e63a74d9b2c1
Revises: d52f8e901c4b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e63a74d9b2c1"
down_revision: str | None = "d52f8e901c4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "payroll_periods",
    "employee_pay_rates",
    "payroll_provider_mappings",
    "payroll_exports",
    "payroll_export_lines",
)


def _base_columns() -> list[sa.Column]:
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
    period_status = _enum(
        "payrollperiodstatus",
        "OPEN",
        "EMPLOYEE_REVIEW",
        "SUPERVISOR_REVIEW",
        "PAYROLL_REVIEW",
        "LOCKED",
        "EXPORTED",
        "PROCESSED",
        "RECONCILED",
    )
    period_export_status = _enum(
        "payrollperiodexportstatus",
        "NOT_STARTED",
        "GENERATED",
        "PROCESSED",
    )
    reconciliation_status = _enum(
        "payrollreconciliationstatus",
        "NOT_STARTED",
        "IN_PROGRESS",
        "EXCEPTIONS",
        "RECONCILED",
    )
    mapping_type = _enum(
        "payrollmappingtype",
        "EMPLOYEE",
        "EARNING",
        "DEDUCTION",
        "PROJECT",
        "COST_CODE",
        "DEPARTMENT",
        "LABOR_CATEGORY",
        "LEAVE",
    )
    export_format = _enum("payrollexportformat", "CSV", "XLSX", "JSON")
    export_status = _enum(
        "payrollexportstatus",
        "GENERATED",
        "TRANSMITTED",
        "ACKNOWLEDGED",
        "FAILED",
    )
    for enum in (
        period_status,
        period_export_status,
        reconciliation_status,
        mapping_type,
        export_format,
        export_status,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payroll_periods",
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("status", period_status, nullable=False),
        sa.Column("workweek_definition", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("approved_by", sa.Uuid()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("export_status", period_export_status, nullable=False),
        sa.Column("reconciliation_status", reconciliation_status, nullable=False),
        sa.Column("review_reason", sa.Text()),
        sa.Column("validation_snapshot", sa.JSON()),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "period_start", "period_end"),
    )
    op.create_index("ix_payroll_periods_tenant_id", "payroll_periods", ["tenant_id"])
    op.create_index(
        "ix_payroll_period_tenant_status",
        "payroll_periods",
        ["tenant_id", "status"],
    )

    op.create_table(
        "employee_pay_rates",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("base_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("overtime_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("double_time_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("fringe_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("cash_in_lieu_rate", sa.Numeric(12, 4), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "employee_id", "effective_from"),
    )
    op.create_index("ix_employee_pay_rates_tenant_id", "employee_pay_rates", ["tenant_id"])
    op.create_index(
        "ix_pay_rate_tenant_employee_dates",
        "employee_pay_rates",
        ["tenant_id", "employee_id", "effective_from"],
    )

    op.create_table(
        "payroll_provider_mappings",
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("mapping_type", mapping_type, nullable=False),
        sa.Column("internal_key", sa.String(length=200), nullable=False),
        sa.Column("external_code", sa.String(length=200), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("configuration", sa.JSON(), nullable=False),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "mapping_type",
            "internal_key",
            "effective_from",
        ),
    )
    op.create_index(
        "ix_payroll_provider_mappings_tenant_id",
        "payroll_provider_mappings",
        ["tenant_id"],
    )
    op.create_index(
        "ix_payroll_mapping_lookup",
        "payroll_provider_mappings",
        ["tenant_id", "provider", "mapping_type", "internal_key"],
    )

    op.create_table(
        "payroll_exports",
        sa.Column("payroll_period_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("format", export_format, nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.Uuid(), nullable=False),
        sa.Column("file_checksum", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False),
        sa.Column("status", export_status, nullable=False),
        sa.Column("includes_sensitive_fields", sa.Boolean(), nullable=False),
        sa.Column("totals_snapshot", sa.JSON(), nullable=False),
        sa.Column("provider_reference", sa.String(length=300)),
        sa.Column("transmitted_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_period_id"],
            ["payroll_periods.tenant_id", "payroll_periods.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "payroll_period_id",
            "provider",
            "format",
            "artifact_version",
        ),
    )
    op.create_index("ix_payroll_exports_tenant_id", "payroll_exports", ["tenant_id"])
    op.create_index(
        "ix_payroll_export_tenant_period",
        "payroll_exports",
        ["tenant_id", "payroll_period_id"],
    )

    op.create_table(
        "payroll_export_lines",
        sa.Column("payroll_export_id", sa.Uuid(), nullable=False),
        sa.Column("time_entry_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("employee_number", sa.String(length=50), nullable=False),
        sa.Column("employee_name", sa.String(length=220), nullable=False),
        sa.Column("provider_employee_id", sa.String(length=200), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("regular_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("double_time_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("travel_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("leave_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("indirect_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("project_code", sa.String(length=200)),
        sa.Column("cost_code", sa.String(length=200)),
        sa.Column("charge_code", sa.String(length=100), nullable=False),
        sa.Column("contract_code", sa.String(length=100)),
        sa.Column("task_order", sa.String(length=100)),
        sa.Column("clin", sa.String(length=100)),
        sa.Column("funding_line", sa.String(length=100)),
        sa.Column("labor_category", sa.String(length=100)),
        sa.Column("work_classification", sa.String(length=150)),
        sa.Column("wage_determination", sa.String(length=150)),
        sa.Column("base_rate", sa.Numeric(12, 4)),
        sa.Column("overtime_rate", sa.Numeric(12, 4)),
        sa.Column("double_time_rate", sa.Numeric(12, 4)),
        sa.Column("fringe_rate", sa.Numeric(12, 4)),
        sa.Column("cash_in_lieu_rate", sa.Numeric(12, 4)),
        sa.Column("gross_labor", sa.Numeric(14, 2)),
        sa.Column("job_cost_amount", sa.Numeric(14, 2)),
        sa.Column("mapping_snapshot", sa.JSON(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_export_id"],
            ["payroll_exports.tenant_id", "payroll_exports.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "time_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "payroll_export_id", "time_entry_id"),
    )
    op.create_index(
        "ix_payroll_export_lines_tenant_id",
        "payroll_export_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_payroll_export_line_tenant_export",
        "payroll_export_lines",
        ["tenant_id", "payroll_export_id"],
    )
    for table in TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.drop_table(table)
    for name in (
        "payrollexportstatus",
        "payrollexportformat",
        "payrollmappingtype",
        "payrollreconciliationstatus",
        "payrollperiodexportstatus",
        "payrollperiodstatus",
    ):
        op.execute(f"DROP TYPE {name}")


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _enable_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""CREATE POLICY tenant_isolation ON "{table}"
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
    )
