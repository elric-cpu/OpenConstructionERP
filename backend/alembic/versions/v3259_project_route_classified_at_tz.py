"""Make project-route classification timestamps timezone-aware.

``RouteService`` records ``classified_at`` with an aware UTC datetime, while
the original model declared the column as ``TIMESTAMP WITHOUT TIME ZONE``.
asyncpg rejects that mismatch before the assessment can be created. Existing
naive values were emitted as UTC, so the conversion interprets them explicitly
in UTC rather than relying on the database session timezone.

Inspector-guarded so fresh databases, which already receive the corrected ORM
shape through ``Base.metadata.create_all()``, remain a no-op.

Revision ID: v3259_project_route_classified_at_tz
Revises: v3258_progress_entry_seq
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3259_project_route_classified_at_tz"
down_revision: Union[str, Sequence[str], None] = "v3258_progress_entry_seq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "oe_project_route_assessment"
_COLUMN = "classified_at"


def _column_type() -> sa.types.TypeEngine | None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return None
    return next(
        (column["type"] for column in inspector.get_columns(_TABLE) if column["name"] == _COLUMN),
        None,
    )


def upgrade() -> None:
    column_type = _column_type()
    if column_type is None or getattr(column_type, "timezone", False):
        return

    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.DateTime(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using=f"{_COLUMN} AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    column_type = _column_type()
    if column_type is None or not getattr(column_type, "timezone", False):
        return

    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
        postgresql_using=f"{_COLUMN} AT TIME ZONE 'UTC'",
    )
