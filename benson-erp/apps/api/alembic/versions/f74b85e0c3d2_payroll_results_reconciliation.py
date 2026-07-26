"""payroll_results_reconciliation

Revision ID: f74b85e0c3d2
Revises: e63a74d9b2c1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f74b85e0c3d2"
down_revision: str | None = "e63a74d9b2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "payroll_result_imports",
    "payroll_result_lines",
    "payroll_reconciliation_exceptions",
    "payroll_job_costs",
)


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    import_status = postgresql.ENUM(
        "IMPORTED",
        "EXCEPTIONS",
        "RECONCILED",
        name="payrollresultimportstatus",
        create_type=False,
    )
    exception_status = postgresql.ENUM(
        "OPEN",
        "RESOLVED",
        name="reconciliationexceptionstatus",
        create_type=False,
    )
    import_status.create(op.get_bind(), checkfirst=True)
    exception_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payroll_result_imports",
        sa.Column("payroll_period_id", sa.Uuid(), nullable=False),
        sa.Column("payroll_export_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_reference", sa.String(300), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.Uuid(), nullable=False),
        sa.Column("status", import_status, nullable=False),
        sa.Column("reconciliation_summary", sa.JSON()),
        sa.Column("reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("reconciled_by", sa.Uuid()),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_period_id"],
            ["payroll_periods.tenant_id", "payroll_periods.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_export_id"],
            ["payroll_exports.tenant_id", "payroll_exports.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "payroll_export_id"),
        sa.UniqueConstraint("tenant_id", "provider", "provider_reference"),
    )
    op.create_index("ix_payroll_result_imports_tenant_id", "payroll_result_imports", ["tenant_id"])
    op.create_index(
        "ix_payroll_result_import_period",
        "payroll_result_imports",
        ["tenant_id", "payroll_period_id"],
    )

    op.create_table(
        "payroll_result_lines",
        sa.Column("payroll_result_import_id", sa.Uuid(), nullable=False),
        sa.Column("payroll_export_line_id", sa.Uuid(), nullable=False),
        sa.Column("time_entry_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("provider_employee_id", sa.String(200), nullable=False),
        sa.Column("provider_payroll_id", sa.String(300)),
        sa.Column("payment_reference", sa.String(300)),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("regular_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("double_time_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("travel_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("leave_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("indirect_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("base_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("overtime_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("double_time_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("gross_wages", sa.Numeric(14, 2), nullable=False),
        sa.Column("employer_taxes", sa.Numeric(14, 2), nullable=False),
        sa.Column("employee_deductions", sa.Numeric(14, 2), nullable=False),
        sa.Column("employer_benefits", sa.Numeric(14, 2), nullable=False),
        sa.Column("workers_compensation", sa.Numeric(14, 2), nullable=False),
        sa.Column("fringe_benefits", sa.Numeric(14, 2), nullable=False),
        sa.Column("net_pay", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_adjustment", sa.Boolean(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_result_import_id"],
            ["payroll_result_imports.tenant_id", "payroll_result_imports.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_export_line_id"],
            ["payroll_export_lines.tenant_id", "payroll_export_lines.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "time_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "payroll_result_import_id", "time_entry_id"),
    )
    op.create_index("ix_payroll_result_lines_tenant_id", "payroll_result_lines", ["tenant_id"])
    op.create_index(
        "ix_payroll_result_line_import",
        "payroll_result_lines",
        ["tenant_id", "payroll_result_import_id"],
    )

    op.create_table(
        "payroll_reconciliation_exceptions",
        sa.Column("payroll_result_import_id", sa.Uuid(), nullable=False),
        sa.Column("payroll_result_line_id", sa.Uuid()),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.String(300)),
        sa.Column("actual_value", sa.String(300)),
        sa.Column("status", exception_status, nullable=False),
        sa.Column("resolution_reason", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.Uuid()),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_result_import_id"],
            ["payroll_result_imports.tenant_id", "payroll_result_imports.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_result_line_id"],
            ["payroll_result_lines.tenant_id", "payroll_result_lines.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_index(
        "ix_payroll_reconciliation_exceptions_tenant_id",
        "payroll_reconciliation_exceptions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_payroll_reconciliation_exception_import",
        "payroll_reconciliation_exceptions",
        ["tenant_id", "payroll_result_import_id", "status"],
    )

    op.create_table(
        "payroll_job_costs",
        sa.Column("payroll_result_line_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("cost_code", sa.String(200)),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("direct_wages", sa.Numeric(14, 2), nullable=False),
        sa.Column("employer_taxes", sa.Numeric(14, 2), nullable=False),
        sa.Column("employer_benefits", sa.Numeric(14, 2), nullable=False),
        sa.Column("workers_compensation", sa.Numeric(14, 2), nullable=False),
        sa.Column("fringe_benefits", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("calculation_snapshot", sa.JSON(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "payroll_result_line_id"],
            ["payroll_result_lines.tenant_id", "payroll_result_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "payroll_result_line_id"),
    )
    op.create_index("ix_payroll_job_costs_tenant_id", "payroll_job_costs", ["tenant_id"])
    op.create_index(
        "ix_payroll_job_cost_project",
        "payroll_job_costs",
        ["tenant_id", "project_id", "cost_code"],
    )
    for table in TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.drop_table(table)
    op.execute("DROP TYPE reconciliationexceptionstatus")
    op.execute("DROP TYPE payrollresultimportstatus")


def _enable_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY tenant_isolation ON "{table}" '
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )
