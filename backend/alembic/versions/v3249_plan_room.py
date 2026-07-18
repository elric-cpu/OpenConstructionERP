# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plan Room register - positioned photo / note pins.

Creates ``oe_plan_pin``: a positioned pin dropped on a document page, storing
its normalized (x, y) page coordinate, an optional note and photo reference, and
the document revision it was authored against. The overlay composite (defect
pins, markups, measurements, photos) is read from the owning modules at request
time and never stored here.

GUID columns are VARCHAR(36) (the app.database.GUID TypeDecorator impl);
``project_id`` carries a real FK to the project with cascade delete, so pins die
with their project. ``document_id`` is a plain VARCHAR so a pin can point at any
viewable document without a cross-module FK. Coordinates are FLOAT; ``metadata``
is JSON defaulting to ``{}``; the timestamps are tz-aware.

The embedded-PostgreSQL runtime materialises this table via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Every step is inspector-guarded, so a re-run (or a
DB the runtime already auto-created) is a no-op. Additive: no existing table is
touched. Chained after v3248_commissioning to keep a single linear head.
PostgreSQL-only.

Revision ID: v3249_plan_room
Revises: v3248_commissioning
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3249_plan_room"
down_revision = "v3248_commissioning"
branch_labels = None
depends_on = None

_PIN = "oe_plan_pin"


def _has_table(name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _create_pin() -> None:
    if _has_table(_PIN):
        return
    op.create_table(
        _PIN,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(length=255), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("photo_ref", sa.String(length=500), nullable=True),
        sa.Column("file_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_plan_pin_project", _PIN, ["project_id"])
    op.create_index("ix_plan_pin_document", _PIN, ["document_id"])
    op.create_index("ix_plan_pin_document_page", _PIN, ["document_id", "page"])


def upgrade() -> None:
    """Create the plan-room pin table (idempotent)."""
    _create_pin()


def downgrade() -> None:
    """Drop the plan-room pin table (idempotent)."""
    if _has_table(_PIN):
        op.drop_table(_PIN)
