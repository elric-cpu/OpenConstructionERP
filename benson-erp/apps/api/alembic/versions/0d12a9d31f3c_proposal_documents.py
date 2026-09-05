"""proposal_documents

Revision ID: 0d12a9d31f3c
Revises: 0232a8dbc760
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0d12a9d31f3c"
down_revision: str | None = "0232a8dbc760"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column(
        "organizations", sa.Column("logo_storage_key", sa.String(length=1000), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column(
            "primary_color",
            sa.String(length=7),
            server_default=sa.text("'#722F37'"),
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "secondary_color",
            sa.String(length=7),
            server_default=sa.text("'#F5F1E8'"),
            nullable=False,
        ),
    )
    op.alter_column("organizations", "primary_color", server_default=None)
    op.alter_column("organizations", "secondary_color", server_default=None)
    op.create_table(
        "documents",
        sa.Column("record_type", sa.String(length=80), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "visibility",
            sa.Enum("INTERNAL", "CLIENT", name="documentvisibility"),
            nullable=False,
        ),
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
        sa.UniqueConstraint("tenant_id", "storage_key"),
    )
    op.create_index("ix_documents_record_id", "documents", ["record_id"])
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.add_column("proposals", sa.Column("acceptance_user_agent", sa.String(1000)))
    op.add_column("proposals", sa.Column("acceptance_statement", sa.Text()))
    op.add_column("proposals", sa.Column("accepted_document_checksum", sa.String(64)))
    op.add_column("proposals", sa.Column("document_id", sa.Uuid()))
    op.execute('ALTER TABLE "documents" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "documents" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON "documents"
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "documents"')
    op.execute('ALTER TABLE "documents" DISABLE ROW LEVEL SECURITY')
    op.drop_column("proposals", "document_id")
    op.drop_column("proposals", "accepted_document_checksum")
    op.drop_column("proposals", "acceptance_statement")
    op.drop_column("proposals", "acceptance_user_agent")
    op.drop_index("ix_documents_tenant_id", table_name="documents")
    op.drop_index("ix_documents_record_id", table_name="documents")
    op.drop_table("documents")
    op.execute("DROP TYPE documentvisibility")
    op.drop_column("organizations", "secondary_color")
    op.drop_column("organizations", "primary_color")
    op.drop_column("organizations", "logo_storage_key")
    op.drop_column("organizations", "phone")
