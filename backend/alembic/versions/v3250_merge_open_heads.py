# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Merge the open alembic heads back into one.

Parallel work since the last merge point left four open heads: the earlier
merge revision itself (``v3230_merge_estimate_costexplorer_heads``), the cost
search trigram index (``v3234_cost_search_trgm``), the defects liability
register (``v3244_defects_liability``) and the plan room overlays
(``v3249_plan_room``). With more than one head a plain ``alembic upgrade head``
or ``alembic stamp head`` fails with "Multiple heads are present", which bit us
during an external PostgreSQL cutover before.

This is a pure merge point: no schema change, it only rejoins the lineages so
the history has a single unambiguous head again. The embedded runtime that
builds its schema through ``create_all`` is unaffected either way.

Revision ID: v3250_merge_open_heads
Revises: v3230_merge_estimate_costexplorer_heads, v3234_cost_search_trgm, v3244_defects_liability, v3249_plan_room
Create Date: 2026-07-18
"""

from __future__ import annotations

revision = "v3250_merge_open_heads"
down_revision = (
    "v3230_merge_estimate_costexplorer_heads",
    "v3234_cost_search_trgm",
    "v3244_defects_liability",
    "v3249_plan_room",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: this revision only merges open heads, it changes no schema."""


def downgrade() -> None:
    """No-op: re-splitting a merge point back into separate heads is not supported."""
