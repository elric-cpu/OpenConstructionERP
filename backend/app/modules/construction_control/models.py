# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Construction-control ORM models.

Tables:
    oe_cc_acceptance_criterion - referenceable acceptance clause + tolerance +
        standard reference; every inspection result is judged against one of these.
    oe_cc_inspection           - one inspection record with a type discriminator
        (mir / wir / ir / hidden_works / acceptance) and a recorded pass/fail result.
    oe_cc_element_ref          - the Universal Element Reference (UER): a polymorphic
        link from any control record to a model element, regardless of source format
        (IFC, Revit, DWG, DGN, ...). Resolves through the normalised bim_hub identity
        ``(model_id, stable_id)`` so IFC GlobalId is optional, never required.

Design note: the UER is a shared table rather than columns inlined on each record,
so one resolver and one schema serve inspections today and NCR / test results /
material records / as-built records as later pillars land.
"""

import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class AcceptanceCriterion(Base):
    """A referenceable acceptance clause: what is measured, against which standard,
    and the tolerance that decides pass or fail."""

    __tablename__ = "oe_cc_acceptance_criterion"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_oe_cc_criterion_project_code"),
        Index("ix_oe_cc_criterion_project", "project_id"),
        Index("ix_oe_cc_criterion_project_category", "project_id", "category"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Open-standard anchor, e.g. "ISO 9001:2015 8.6", "EN 1992-1-1", "ACI 318",
    # "AS 3600", "BS 8500", "GOST/SP 70.13330". Free text - never an enum.
    standard_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # What is measured, e.g. "cube compressive strength", "weld throat thickness".
    characteristic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # How to verify - test/inspection method reference.
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # How a measured value is judged against this criterion:
    # range | min | max | boolean | text. Drives the pass/fail decision.
    acceptance_rule: Mapped[str] = mapped_column(String(20), nullable=False, default="text", server_default="text")
    # Numeric bounds kept as strings (consistent with the platform's money/quantity
    # convention) so arbitrary precision survives the JSON/SQL round trip.
    nominal_value: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tolerance_lower: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tolerance_upper: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="1", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<AcceptanceCriterion {self.code} - {self.title[:40]}>"


class Inspection(Base):
    """A single inspection / acceptance act on a work location or model element.

    One entity serves every phase-specific document through the ``inspection_type``
    discriminator (material / witness / final / hidden-works / acceptance), and every
    legal regime through ``party_role`` (contractor QC, client/engineer QA, third-party
    inspection, authority having jurisdiction).
    """

    __tablename__ = "oe_cc_inspection"
    __table_args__ = (
        UniqueConstraint("project_id", "inspection_number", name="uq_oe_cc_inspection_project_number"),
        Index("ix_oe_cc_inspection_project", "project_id"),
        Index("ix_oe_cc_inspection_project_status", "project_id", "status"),
        Index("ix_oe_cc_inspection_project_type", "project_id", "inspection_type"),
        Index("ix_oe_cc_inspection_criterion", "criterion_id"),
        Index("ix_oe_cc_inspection_raised_ncr", "raised_ncr_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    inspection_number: Mapped[str] = mapped_column(String(20), nullable=False)
    # mir | wir | ir | hidden_works | acceptance
    inspection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Viewpoint that produced the record: qc | qa | tpi | ahj.
    party_role: Mapped[str] = mapped_column(String(10), nullable=False, default="qc", server_default="qc")
    # Intervention-point class (Pillar 5 gating hook): hold | witness | surveillance | review.
    intervention_point: Mapped[str | None] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Cross-module soft links (plain ids, no FK): schedule activity, acceptance criterion.
    activity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    criterion_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # draft | scheduled | in_progress | passed | failed | closed | void
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft")
    # pass | fail | conditional (set when a result is recorded)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    measured_value: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NCR auto-raised when the inspection fails; links back via NCR.linked_inspection_id.
    raised_ncr_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    scheduled_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    performed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<Inspection {self.inspection_number} {self.inspection_type} ({self.status})>"


class ElementRef(Base):
    """Universal Element Reference (UER).

    A polymorphic link attaching any control record to a model element regardless of
    the source format. The strong link is ``bim_element_id``; failing that the element
    resolves from the normalised ``(model_id, stable_id)`` identity, then from
    ``(model_id, native_id)``. Display fields are denormalised so a record renders even
    when the model is offline or not yet ingested. ``ifc_global_id`` is an optional
    open-standard crosswalk that gates BCF round-trip; it is never required.
    """

    __tablename__ = "oe_cc_element_ref"
    __table_args__ = (
        Index("ix_oe_cc_element_ref_owner", "owner_type", "owner_id"),
        Index("ix_oe_cc_element_ref_model_stable", "model_id", "stable_id"),
        Index("ix_oe_cc_element_ref_project", "project_id"),
        Index("ix_oe_cc_element_ref_element", "bim_element_id"),
    )

    # Polymorphic owner: inspection | ncr | criterion | test_result | material_record | asbuilt.
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Denormalised so every UER is tenant-scoped on its own (IDOR defence + fast filter).
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Strong link; SET NULL on element delete keeps the row resolvable via stable_id.
    bim_element_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_bim_element.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("oe_bim_model.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Normalised per-format id (IFC GlobalId / Revit UniqueId / DWG handle / DGN id).
    stable_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ifc / revit / dwg / dxf / dgn / nwd / pointcloud / other.
    source_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Optional open-standard crosswalk (BCF). 22-char IFC GlobalId.
    ifc_global_id: Mapped[str | None] = mapped_column(String(22), nullable=True)
    # Raw source id when it differs from stable_id (Revit ElementId vs UniqueId).
    native_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Audit-critical: the model revision the record was made against ("accepted vs rev C").
    model_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    element_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    element_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    viewpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[dict] = mapped_column(  # type: ignore[assignment]
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<ElementRef {self.owner_type}:{self.owner_id} -> {self.source_format}:{self.stable_id}>"
