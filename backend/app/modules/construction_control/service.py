# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Construction-control service - acceptance criteria, inspections and the
failed-inspection -> NCR bridge.

The service owns the business rules that turn a recorded inspection result into a
non-conformance report: a ``fail`` (or ``conditional``) raises an NCR through the
existing NCR module, links it back to the inspection, and never raises twice for the
same inspection.
"""

import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.json_merge import merge_metadata
from app.modules.construction_control.models import (
    AcceptanceCriterion,
    ElementRef,
    Inspection,
)
from app.modules.construction_control.repository import (
    CriterionRepository,
    ElementRefRepository,
    InspectionRepository,
)
from app.modules.construction_control.schemas import (
    AcceptanceCriterionCreate,
    AcceptanceCriterionUpdate,
    InspectionCreate,
    InspectionResultIn,
    InspectionUpdate,
)
from app.modules.construction_control.uer import is_empty_ref, resolve_element_ref

logger = logging.getLogger(__name__)

# Recording a result is only meaningful while the inspection is still open.
_RECORDABLE_STATUSES = {"draft", "scheduled", "in_progress"}

# Result -> (inspection status, NCR severity default, raise-NCR?).
_RESULT_RULES: dict[str, tuple[str, str, bool]] = {
    "pass": ("passed", "", False),
    "fail": ("failed", "major", True),
    # Accepted subject to a tracked observation: passes the gate, raises a low NCR.
    "conditional": ("passed", "observation", True),
}

# Inspection type -> NCR type (must match the NCR schema's pattern). Incoming-material
# inspections map to material non-conformances; everything else to workmanship.
_NCR_TYPE_BY_INSPECTION = {"mir": "material"}


class ConstructionControlService:
    """Business logic for the universal construction-control core (Pillar 1)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.criteria = CriterionRepository(session)
        self.inspections = InspectionRepository(session)
        self.element_refs = ElementRefRepository(session)

    # ── Acceptance criteria ──────────────────────────────────────────────────

    async def create_criterion(self, data: AcceptanceCriterionCreate, user_id: str | None) -> AcceptanceCriterion:
        criterion = AcceptanceCriterion(
            project_id=data.project_id,
            code=data.code,
            title=data.title,
            description=data.description,
            standard_ref=data.standard_ref,
            discipline=data.discipline,
            category=data.category,
            characteristic=data.characteristic,
            method=data.method,
            unit=data.unit,
            acceptance_rule=data.acceptance_rule,
            nominal_value=data.nominal_value,
            tolerance_lower=data.tolerance_lower,
            tolerance_upper=data.tolerance_upper,
            is_active=data.is_active,
            created_by=user_id,
            metadata_=data.metadata,
        )
        criterion = await self.criteria.create(criterion)
        logger.info("Acceptance criterion created: %s for project %s", data.code, data.project_id)
        return criterion

    async def get_criterion(self, criterion_id: uuid.UUID) -> AcceptanceCriterion:
        criterion = await self.criteria.get_by_id(criterion_id)
        if criterion is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acceptance criterion not found")
        return criterion

    async def list_criteria(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[AcceptanceCriterion], int]:
        return await self.criteria.list_for_project(
            project_id, offset=offset, limit=limit, category=category, is_active=is_active
        )

    async def update_criterion(self, criterion_id: uuid.UUID, data: AcceptanceCriterionUpdate) -> AcceptanceCriterion:
        criterion = await self.get_criterion(criterion_id)
        fields = self._merge_metadata_patch(data.model_dump(exclude_unset=True), criterion)
        if not fields:
            return criterion
        await self.criteria.update_fields(criterion_id, **fields)
        await self.session.refresh(criterion)
        return criterion

    async def delete_criterion(self, criterion_id: uuid.UUID) -> None:
        await self.get_criterion(criterion_id)
        await self.criteria.delete(criterion_id)

    # ── Inspections ──────────────────────────────────────────────────────────

    async def create_inspection(self, data: InspectionCreate, user_id: str | None) -> Inspection:
        # Cross-project criterion is an IDOR vector: confirm it lives in this project.
        if data.criterion_id is not None:
            criterion = await self.get_criterion(data.criterion_id)
            if criterion.project_id != data.project_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Acceptance criterion not found in this project",
                )

        inspection = Inspection(
            project_id=data.project_id,
            inspection_type=data.inspection_type,
            party_role=data.party_role,
            intervention_point=data.intervention_point,
            title=data.title,
            description=data.description,
            location_description=data.location_description,
            activity_id=data.activity_id,
            criterion_id=str(data.criterion_id) if data.criterion_id else None,
            status="scheduled" if data.scheduled_at else "draft",
            scheduled_at=data.scheduled_at,
            created_by=user_id,
            metadata_=data.metadata,
        )
        inspection = await self.inspections.create(inspection)

        # Persist the element link (UER). The resolver enforces that any referenced
        # model/element belongs to this project, so this is also an IDOR checkpoint.
        if not is_empty_ref(data.element):
            await self._attach_element(inspection, data.element)

        logger.info(
            "Inspection created: %s (%s) project %s",
            inspection.inspection_number,
            data.inspection_type,
            data.project_id,
        )
        return inspection

    async def get_inspection(self, inspection_id: uuid.UUID) -> Inspection:
        inspection = await self.inspections.get_by_id(inspection_id)
        if inspection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection not found")
        return inspection

    async def list_inspections(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        inspection_type: str | None = None,
        status_filter: str | None = None,
        party_role: str | None = None,
    ) -> tuple[list[Inspection], int]:
        return await self.inspections.list_for_project(
            project_id,
            offset=offset,
            limit=limit,
            inspection_type=inspection_type,
            status=status_filter,
            party_role=party_role,
        )

    async def update_inspection(self, inspection_id: uuid.UUID, data: InspectionUpdate) -> Inspection:
        inspection = await self.get_inspection(inspection_id)
        if inspection.status in ("closed", "void"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit an inspection with status '{inspection.status}'",
            )
        fields = data.model_dump(exclude_unset=True)
        if "criterion_id" in fields and fields["criterion_id"] is not None:
            fields["criterion_id"] = str(fields["criterion_id"])
        fields = self._merge_metadata_patch(fields, inspection)
        if not fields:
            return inspection
        await self.inspections.update_fields(inspection_id, **fields)
        await self.session.refresh(inspection)
        return inspection

    async def delete_inspection(self, inspection_id: uuid.UUID) -> None:
        inspection = await self.get_inspection(inspection_id)
        await self.element_refs.delete_for_owner("inspection", str(inspection.id))
        await self.inspections.delete(inspection_id)

    async def record_result(
        self,
        inspection_id: uuid.UUID,
        data: InspectionResultIn,
        user_id: str | None,
    ) -> Inspection:
        """Record a pass/fail/conditional. A fail (or conditional) raises a linked NCR."""
        inspection = await self.get_inspection(inspection_id)
        if inspection.status not in _RECORDABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot record a result on an inspection with status '{inspection.status}'. "
                    "A result can only be recorded while the inspection is open."
                ),
            )

        new_status, default_severity, raise_ncr = _RESULT_RULES[data.result]

        await self.inspections.update_fields(
            inspection_id,
            result=data.result,
            status=new_status,
            measured_value=data.measured_value,
            result_notes=data.notes,
            performed_at=data.performed_at,
            performed_by=user_id,
        )
        await self.session.refresh(inspection)

        if raise_ncr:
            severity = data.ncr_severity or default_severity
            ncr_id = await self._raise_ncr_for_failure(inspection, severity=severity, user_id=user_id)
            await self.inspections.update_fields(inspection_id, raised_ncr_id=ncr_id)
            await self.session.refresh(inspection)
            logger.info("Inspection %s -> %s raised NCR %s", inspection.inspection_number, data.result, ncr_id)

        return inspection

    # ── Element links (UER) ──────────────────────────────────────────────────

    async def _attach_element(self, inspection: Inspection, ref_in) -> ElementRef:
        resolved = await resolve_element_ref(self.session, inspection.project_id, ref_in)
        ref = ElementRef(
            owner_type="inspection",
            owner_id=str(inspection.id),
            project_id=inspection.project_id,
            **resolved,
        )
        return await self.element_refs.add(ref)

    async def elements_for(self, inspection_id: uuid.UUID) -> list[ElementRef]:
        return await self.element_refs.list_for_owner("inspection", str(inspection_id))

    async def elements_for_many(self, inspection_ids: list[uuid.UUID]) -> dict[str, list[ElementRef]]:
        return await self.element_refs.list_for_owners("inspection", [str(i) for i in inspection_ids])

    # ── Internals ──────────────────────────────────────────────────────────--

    async def _raise_ncr_for_failure(self, inspection: Inspection, *, severity: str, user_id: str | None) -> str:
        """Create an NCR for a failed/conditional inspection via the NCR module.

        Lazy-imported so the construction-control module degrades gracefully if the
        NCR module is ever disabled (it then records the failure without an NCR).
        """
        from app.modules.ncr.schemas import NCRCreate
        from app.modules.ncr.service import NCRService

        ncr_type = _NCR_TYPE_BY_INSPECTION.get(inspection.inspection_type, "workmanship")
        criterion_clause = ""
        if inspection.criterion_id:
            try:
                criterion = await self.criteria.get_by_id(uuid.UUID(inspection.criterion_id))
            except (ValueError, TypeError):
                criterion = None
            if criterion is not None:
                bounds = " / ".join(
                    p
                    for p in (
                        f"nominal {criterion.nominal_value}" if criterion.nominal_value else "",
                        f">= {criterion.tolerance_lower}" if criterion.tolerance_lower else "",
                        f"<= {criterion.tolerance_upper}" if criterion.tolerance_upper else "",
                    )
                    if p
                )
                criterion_clause = (
                    f"\n\nJudged against criterion {criterion.code} ({criterion.title})"
                    + (f", standard {criterion.standard_ref}" if criterion.standard_ref else "")
                    + (f". Tolerance: {bounds}." if bounds else ".")
                    + (f" Measured: {inspection.measured_value}." if inspection.measured_value else "")
                )

        description_parts = [
            f"Raised automatically from inspection {inspection.inspection_number} "
            f"({inspection.inspection_type}).",
        ]
        if inspection.description:
            description_parts.append(inspection.description)
        if inspection.result_notes:
            description_parts.append(f"Notes: {inspection.result_notes}")
        description = "".join(("\n\n".join(description_parts), criterion_clause)) or inspection.title

        data = NCRCreate(
            project_id=inspection.project_id,
            title=f"Failed inspection {inspection.inspection_number}: {inspection.title}"[:500],
            description=description[:10000],
            ncr_type=ncr_type,
            severity=severity,
            status="identified",
            location_description=inspection.location_description,
            linked_inspection_id=str(inspection.id),
            metadata={
                "source": "construction_control",
                "inspection_id": str(inspection.id),
                "inspection_number": inspection.inspection_number,
                "inspection_type": inspection.inspection_type,
                "result": inspection.result,
                "criterion_id": inspection.criterion_id,
                "measured_value": inspection.measured_value,
            },
        )
        ncr = await NCRService(self.session).create_ncr(data, user_id=user_id)
        return str(ncr.id)

    @staticmethod
    def _merge_metadata_patch(fields: dict[str, Any], instance: object) -> dict[str, Any]:
        """Translate a Pydantic ``metadata`` patch into a merged ``metadata_`` update.

        A PATCH touching one metadata key must not wipe the rest (the same json-overwrite
        defence the rest of the platform applies).
        """
        if "metadata" in fields:
            incoming = fields.pop("metadata")
            if isinstance(incoming, dict):
                fields["metadata_"] = merge_metadata(getattr(instance, "metadata_", None), incoming)
            elif incoming is not None:
                fields["metadata_"] = incoming
        return fields
