"""federal_labor_accounting

Revision ID: 1a2c9d8e4f60
Revises: f74b85e0c3d2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1a2c9d8e4f60"
down_revision: str | None = "f74b85e0c3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "federal_charge_codes",
    "federal_labor_rates",
    "employee_qualifications",
    "federal_invoice_support",
    "federal_invoice_support_lines",
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
    compliance_profile = _enum(
        "federalcomplianceprofile",
        "COMMERCIAL",
        "FEDERAL_FIXED_PRICE",
        "FEDERAL_COST_REIMBURSEMENT",
        "FEDERAL_TIME_AND_MATERIALS",
        "FEDERAL_LABOR_HOUR",
        "FEDERAL_CONSTRUCTION_WAGE_RATE",
        "FEDERAL_SERVICE_CONTRACT_LABOR",
        "STATE_PREVAILING_WAGE",
        "CUSTOM_COMPLIANCE_PROFILE",
    )
    charge_code_status = _enum("federalchargecodestatus", "OPEN", "CLOSED")
    qualification_status = _enum(
        "employeequalificationstatus",
        "ACTIVE",
        "SUSPENDED",
        "REVOKED",
    )
    invoice_support_status = _enum("federalinvoicesupportstatus", "GENERATED")
    for enum in (
        compliance_profile,
        charge_code_status,
        qualification_status,
        invoice_support_status,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "federal_charge_codes",
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("profile", compliance_profile, nullable=False),
        sa.Column("agency_code", sa.String(100), nullable=False),
        sa.Column("contract_code", sa.String(100), nullable=False),
        sa.Column("task_order", sa.String(100)),
        sa.Column("delivery_order", sa.String(100)),
        sa.Column("clin", sa.String(100)),
        sa.Column("slin", sa.String(100)),
        sa.Column("funding_line", sa.String(100)),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("cost_code", sa.String(100)),
        sa.Column("labor_category", sa.String(100)),
        sa.Column("active_from", sa.Date(), nullable=False),
        sa.Column("active_to", sa.Date()),
        sa.Column("status", charge_code_status, nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", sa.Uuid()),
        sa.Column("closed_reason", sa.Text()),
        sa.Column("required_qualification_code", sa.String(100)),
        *_base_columns(),
        sa.CheckConstraint(
            "active_to IS NULL OR active_to >= active_from",
            name="ck_federal_charge_code_dates",
        ),
        sa.CheckConstraint(
            "(status = 'CLOSED' AND closed_at IS NOT NULL) OR "
            "(status = 'OPEN' AND closed_at IS NULL)",
            name="ck_federal_charge_code_closed_state",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["projects.tenant_id", "projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "code"),
    )
    op.create_index(
        "ix_federal_charge_codes_tenant_id",
        "federal_charge_codes",
        ["tenant_id"],
    )
    op.create_index(
        "ix_federal_charge_code_hierarchy",
        "federal_charge_codes",
        [
            "tenant_id",
            "agency_code",
            "contract_code",
            "task_order",
            "clin",
            "funding_line",
        ],
    )
    op.create_index(
        "ix_federal_charge_code_active",
        "federal_charge_codes",
        ["tenant_id", "status", "active_from", "active_to"],
    )

    op.create_table(
        "federal_labor_rates",
        sa.Column("federal_charge_code_id", sa.Uuid(), nullable=False),
        sa.Column("labor_category", sa.String(100), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("regular_bill_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("overtime_bill_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("double_time_bill_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_reference", sa.String(500)),
        *_base_columns(),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_federal_labor_rate_dates",
        ),
        sa.CheckConstraint(
            "regular_bill_rate >= 0 AND overtime_bill_rate >= 0 "
            "AND double_time_bill_rate >= 0",
            name="ck_federal_labor_rate_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "federal_charge_code_id"],
            ["federal_charge_codes.tenant_id", "federal_charge_codes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "federal_charge_code_id",
            "labor_category",
            "effective_from",
        ),
    )
    op.create_index(
        "ix_federal_labor_rates_tenant_id",
        "federal_labor_rates",
        ["tenant_id"],
    )
    op.create_index(
        "ix_federal_labor_rate_lookup",
        "federal_labor_rates",
        ["tenant_id", "federal_charge_code_id", "labor_category", "effective_from"],
    )

    op.create_table(
        "employee_qualifications",
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("qualification_code", sa.String(100), nullable=False),
        sa.Column("qualification_name", sa.String(200), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("status", qualification_status, nullable=False),
        sa.Column("issuer", sa.String(200)),
        sa.Column("credential_number", sa.String(200)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_by", sa.Uuid()),
        sa.Column("evidence_document_id", sa.Uuid()),
        *_base_columns(),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_employee_qualification_dates",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "qualification_code",
            "effective_from",
        ),
    )
    op.create_index(
        "ix_employee_qualifications_tenant_id",
        "employee_qualifications",
        ["tenant_id"],
    )
    op.create_index(
        "ix_employee_qualification_lookup",
        "employee_qualifications",
        ["tenant_id", "employee_id", "qualification_code", "effective_from"],
    )

    op.create_table(
        "federal_invoice_support",
        sa.Column("contract_code", sa.String(100), nullable=False),
        sa.Column("task_order", sa.String(100)),
        sa.Column("invoice_number", sa.String(100)),
        sa.Column("invoice_period_start", sa.Date(), nullable=False),
        sa.Column("invoice_period_end", sa.Date(), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=False),
        sa.Column("status", invoice_support_status, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by", sa.Uuid(), nullable=False),
        sa.Column("total_approved_hours", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_extended_amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "invoice_period_end >= invoice_period_start",
            name="ck_federal_invoice_support_period",
        ),
        sa.CheckConstraint(
            "total_approved_hours >= 0 AND total_extended_amount >= 0",
            name="ck_federal_invoice_support_totals",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
    )
    op.create_index(
        "ix_federal_invoice_support_tenant_id",
        "federal_invoice_support",
        ["tenant_id"],
    )
    op.create_index(
        "ix_federal_invoice_support_contract_period",
        "federal_invoice_support",
        ["tenant_id", "contract_code", "invoice_period_start", "invoice_period_end"],
    )
    op.create_index(
        "uq_federal_invoice_support_scope_version",
        "federal_invoice_support",
        [
            "tenant_id",
            "contract_code",
            sa.text("COALESCE(task_order, '')"),
            "invoice_period_start",
            "invoice_period_end",
            "artifact_version",
        ],
        unique=True,
    )

    op.create_table(
        "federal_invoice_support_lines",
        sa.Column("federal_invoice_support_id", sa.Uuid(), nullable=False),
        sa.Column("time_entry_id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("employee_name", sa.String(220), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("federal_charge_code_id", sa.Uuid(), nullable=False),
        sa.Column("agency_code", sa.String(100), nullable=False),
        sa.Column("contract_code", sa.String(100), nullable=False),
        sa.Column("task_order", sa.String(100)),
        sa.Column("clin", sa.String(100)),
        sa.Column("funding_line", sa.String(100)),
        sa.Column("labor_category", sa.String(100), nullable=False),
        sa.Column("approved_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("regular_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("overtime_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("double_time_hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("regular_bill_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("overtime_bill_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("double_time_bill_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("extended_amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("qualification_status", sa.String(40), nullable=False),
        sa.Column("qualification_snapshot", sa.JSON(), nullable=False),
        sa.Column("payroll_reconciliation_status", sa.String(40), nullable=False),
        sa.Column("payroll_reconciliation_snapshot", sa.JSON(), nullable=False),
        sa.Column("time_approval_snapshot", sa.JSON(), nullable=False),
        sa.Column("bill_rate_snapshot", sa.JSON(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "approved_hours >= 0 AND regular_hours >= 0 AND overtime_hours >= 0 "
            "AND double_time_hours >= 0 AND regular_bill_rate >= 0 "
            "AND overtime_bill_rate >= 0 AND double_time_bill_rate >= 0 "
            "AND extended_amount >= 0",
            name="ck_federal_invoice_support_line_amounts",
        ),
        sa.CheckConstraint(
            "approved_hours = regular_hours + overtime_hours + double_time_hours",
            name="ck_federal_invoice_support_line_hours",
        ),
        sa.CheckConstraint(
            "extended_amount = ROUND("
            "regular_hours * regular_bill_rate + "
            "overtime_hours * overtime_bill_rate + "
            "double_time_hours * double_time_bill_rate, 2)",
            name="ck_federal_invoice_support_line_formula",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "federal_invoice_support_id"],
            ["federal_invoice_support.tenant_id", "federal_invoice_support.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "time_entry_id"],
            ["time_entries.tenant_id", "time_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "federal_charge_code_id"],
            ["federal_charge_codes.tenant_id", "federal_charge_codes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id",
            "federal_invoice_support_id",
            "time_entry_id",
        ),
    )
    op.create_index(
        "ix_federal_invoice_support_lines_tenant_id",
        "federal_invoice_support_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_federal_invoice_support_line_support",
        "federal_invoice_support_lines",
        ["tenant_id", "federal_invoice_support_id"],
    )
    op.create_index(
        "ix_federal_invoice_support_line_employee_date",
        "federal_invoice_support_lines",
        ["tenant_id", "employee_id", "work_date"],
    )

    op.add_column("time_entries", sa.Column("federal_charge_code_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_time_entries_federal_charge_code",
        "time_entries",
        "federal_charge_codes",
        ["tenant_id", "federal_charge_code_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_time_entry_tenant_federal_charge_code",
        "time_entries",
        ["tenant_id", "federal_charge_code_id"],
    )

    for table in TABLES:
        _enable_rls(table)
    _create_immutable_triggers()


def downgrade() -> None:
    _drop_immutable_triggers()
    op.drop_index("ix_time_entry_tenant_federal_charge_code", table_name="time_entries")
    op.drop_constraint(
        "fk_time_entries_federal_charge_code",
        "time_entries",
        type_="foreignkey",
    )
    op.drop_column("time_entries", "federal_charge_code_id")
    for table in reversed(TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.drop_table(table)
    for name in (
        "federalinvoicesupportstatus",
        "employeequalificationstatus",
        "federalchargecodestatus",
        "federalcomplianceprofile",
    ):
        op.execute(f"DROP TYPE {name}")


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def _enable_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY tenant_isolation ON "{table}" '
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )


def _create_immutable_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_federal_invoice_support_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Federal invoice support records are immutable';
        END;
        $$
        """
    )
    for table in ("federal_invoice_support", "federal_invoice_support_lines"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION prevent_federal_invoice_support_mutation()
            """
        )


def _drop_immutable_triggers() -> None:
    for table in ("federal_invoice_support_lines", "federal_invoice_support"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS prevent_federal_invoice_support_mutation()")
