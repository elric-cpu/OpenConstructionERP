# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Clash detection ORM models.

Tables:
    oe_clash_run     — one interference/clearance analysis over N models
    oe_clash_result  — a single clashing element pair within a run

A ``ClashResult`` snapshots the participating elements' name / discipline /
model so the result list stays meaningful even after the source model is
re-imported and the ``oe_bim_element`` rows are replaced. ``id`` /
``created_at`` / ``updated_at`` come from :class:`app.database.Base`.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import GUID, Base


class ClashRun(Base):
    """‌⁠‍A single clash-detection analysis scoped to one project.

    ``model_ids`` is the set of BIM models fed into the broad phase. With
    one model it is an *internal* (intra-model) clash; with two or more it
    is a *federated* coordination run. ``summary`` caches the rendered
    discipline matrix + per-status counts so the dashboard never has to
    re-aggregate thousands of result rows on every poll.
    """

    __tablename__ = "oe_clash_run"
    __table_args__ = (Index("ix_clash_run_project", "project_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # JSON list[str] of bim_model UUIDs covered by this run.
    model_ids: Mapped[list] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=list, server_default="[]"
    )
    # Hard-clash penetration threshold (metres). A pair counts as a hard
    # clash when the bounding-box interpenetration on its tightest axis
    # exceeds this value — filters out the cosmetic touch of coincident
    # faces (slab-on-wall) while still catching real interferences.
    tolerance_m: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.01, server_default="0.01"
    )
    # Clearance threshold (metres). 0 disables the soft pass; >0 also
    # reports element pairs that do NOT intersect but sit within this gap
    # (e.g. maintenance access around an AHU).
    clearance_m: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )
    # 'cross_discipline' (skip same-discipline pairs — the common default),
    # 'all' (every pair), 'selected' (only discipline_filter pairs) or
    # 'selection_sets' (Navisworks-style Set A × Set B, e.g. walls×pipes).
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="cross_discipline",
        server_default="cross_discipline",
    )
    # Optional allow-list of [discipline_a, discipline_b] pairs to test.
    discipline_filter: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Navisworks-style selection sets (mode='selection_sets'). Each is
    # {"disciplines": [...], "element_types": [...]}; a pair is reported
    # iff one element matches set_a and the other matches set_b (strictly
    # cross). NULL for the other modes.
    set_a: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    set_b: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    element_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_clashes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Cached presentation payload: {"matrix": [...], "disciplines": [...],
    # "by_status": {...}, "by_type": {...}}.
    summary: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    results: Mapped[list["ClashResult"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<ClashRun {self.name} ({self.total_clashes} clashes)>"


class ClashResult(Base):
    """‌⁠‍One clashing element pair (A↔B) inside a :class:`ClashRun`.

    ``status`` drives the review workflow:
    ``new`` → ``active`` → ``reviewed`` → ``approved`` / ``resolved`` /
    ``ignored``. ``approved`` means "intentional, accepted" and
    ``ignored`` means "false positive"; both drop out of the open count.
    """

    __tablename__ = "oe_clash_result"
    __table_args__ = (
        Index("ix_clash_result_run", "run_id"),
        Index("ix_clash_result_run_status", "run_id", "status"),
        Index("ix_clash_result_run_disc", "run_id", "a_discipline", "b_discipline"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_clash_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    a_element_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    b_element_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    a_stable_id: Mapped[str] = mapped_column(String(255), nullable=False)
    b_stable_id: Mapped[str] = mapped_column(String(255), nullable=False)
    a_name: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    b_name: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    a_discipline: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Unassigned"
    )
    b_discipline: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Unassigned"
    )
    # Snapshot of the participating elements' element_type (category /
    # family-type) so the result table can show "Wall ↔ Pipe" and stays
    # meaningful after the source model is re-imported. Empty when the
    # source element had no type.
    a_element_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    b_element_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    a_model_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    b_model_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    # Storey (level) index each element sits on — clustered from real
    # geometry Z by the geometry loader. NULL when the model has no GLB
    # or the loader did not resolve a level. Powers the ``level_matrix``
    # in the run summary, which is the meaningful coordination grid for
    # the common single-discipline intra-model run (where the
    # discipline×discipline matrix collapses to a useless 1×1).
    a_storey: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_storey: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 'hard' (interpenetration) or 'clearance' (proximity, no overlap).
    clash_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="hard", server_default="hard"
    )
    # Tightest-axis interpenetration (m); 0 for clearance clashes.
    penetration_m: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )
    # Gap between the two boxes (m); 0 for hard clashes.
    distance_m: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0"
    )
    cx: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cz: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new", server_default="new"
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bcf_topic_guid: Mapped[str | None] = mapped_column(String(36), nullable=True)

    run: Mapped[ClashRun] = relationship(back_populates="results")

    def __repr__(self) -> str:
        return f"<ClashResult {self.a_name} x {self.b_name} ({self.clash_type})>"
