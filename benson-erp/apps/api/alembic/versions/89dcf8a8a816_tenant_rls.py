"""tenant_rls

Revision ID: 89dcf8a8a816
Revises: 6308b8e6838d
"""

from collections.abc import Sequence

from alembic import op

TENANT_TABLES = (
    "audit_events",
    "budget_lines",
    "contracts",
    "customers",
    "estimate_lines",
    "estimate_sections",
    "estimates",
    "leads",
    "outbox_events",
    "projects",
    "properties",
    "proposals",
)

revision: str = "89dcf8a8a816"
down_revision: str | None = "6308b8e6838d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
                USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)'''
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
