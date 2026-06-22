# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Construction-control data access layer."""

import uuid

from sqlalchemy import Integer as SAInteger
from sqlalchemy import cast, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.construction_control.models import (
    AcceptanceCriterion,
    ElementRef,
    Inspection,
)

# Number-allocation retry cap; a couple of retries cover any realistic concurrency,
# the cap stops a pathological hot loop (same backstop the NCR repository uses).
_NUMBER_RETRY_LIMIT = 5


class CriterionRepository:
    """Data access for acceptance criteria."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, criterion_id: uuid.UUID) -> AcceptanceCriterion | None:
        return await self.session.get(AcceptanceCriterion, criterion_id)

    async def create(self, criterion: AcceptanceCriterion) -> AcceptanceCriterion:
        self.session.add(criterion)
        await self.session.flush()
        return criterion

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        category: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[AcceptanceCriterion], int]:
        base = select(AcceptanceCriterion).where(AcceptanceCriterion.project_id == project_id)
        if category is not None:
            base = base.where(AcceptanceCriterion.category == category)
        if is_active is not None:
            base = base.where(AcceptanceCriterion.is_active == is_active)

        total = (await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        stmt = base.order_by(AcceptanceCriterion.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_fields(self, criterion_id: uuid.UUID, **fields: object) -> None:
        await self.session.execute(
            update(AcceptanceCriterion).where(AcceptanceCriterion.id == criterion_id).values(**fields)
        )
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, criterion_id: uuid.UUID) -> None:
        criterion = await self.get_by_id(criterion_id)
        if criterion is not None:
            await self.session.delete(criterion)
            await self.session.flush()


class InspectionRepository:
    """Data access for inspections, with collision-safe per-project numbering."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, inspection_id: uuid.UUID) -> Inspection | None:
        return await self.session.get(Inspection, inspection_id)

    async def next_inspection_number(self, project_id: uuid.UUID) -> str:
        """Next ``INS-NNN`` from MAX(suffix)+1.

        Only rows matching the canonical ``INS-<digits>`` shape are considered, so a
        legacy or externally-numbered row never breaks the integer cast (PostgreSQL
        casts non-numeric text strictly, unlike SQLite).
        """
        stmt = (
            select(func.coalesce(func.max(cast(func.substr(Inspection.inspection_number, 5), SAInteger)), 0))
            .where(Inspection.project_id == project_id)
            .where(Inspection.inspection_number.regexp_match("^INS-[0-9]+$"))
        )
        max_num = (await self.session.execute(stmt)).scalar_one()
        return f"INS-{max_num + 1:03d}"

    async def create(self, inspection: Inspection) -> Inspection:
        """Insert an inspection, deriving ``inspection_number`` with a retry on collision.

        MAX(suffix)+1 can race two concurrent creates onto the same number; the
        per-project unique constraint turns that into an IntegrityError which we
        roll back via savepoint and retry.
        """
        project_id = inspection.project_id
        for _ in range(_NUMBER_RETRY_LIMIT):
            inspection.inspection_number = await self.next_inspection_number(project_id)
            savepoint = await self.session.begin_nested()
            self.session.add(inspection)
            try:
                await self.session.flush()
            except IntegrityError:
                await savepoint.rollback()
                continue
            return inspection
        raise RuntimeError(f"Could not allocate a unique inspection number for project {project_id}")

    async def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
        inspection_type: str | None = None,
        status: str | None = None,
        party_role: str | None = None,
    ) -> tuple[list[Inspection], int]:
        base = select(Inspection).where(Inspection.project_id == project_id)
        if inspection_type is not None:
            base = base.where(Inspection.inspection_type == inspection_type)
        if status is not None:
            base = base.where(Inspection.status == status)
        if party_role is not None:
            base = base.where(Inspection.party_role == party_role)

        total = (await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        stmt = base.order_by(Inspection.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def update_fields(self, inspection_id: uuid.UUID, **fields: object) -> None:
        await self.session.execute(update(Inspection).where(Inspection.id == inspection_id).values(**fields))
        await self.session.flush()
        self.session.expire_all()

    async def delete(self, inspection_id: uuid.UUID) -> None:
        inspection = await self.get_by_id(inspection_id)
        if inspection is not None:
            await self.session.delete(inspection)
            await self.session.flush()


class ElementRefRepository:
    """Data access for the shared Universal Element Reference table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, ref: ElementRef) -> ElementRef:
        self.session.add(ref)
        await self.session.flush()
        return ref

    async def list_for_owner(self, owner_type: str, owner_id: str) -> list[ElementRef]:
        result = await self.session.execute(
            select(ElementRef)
            .where(ElementRef.owner_type == owner_type)
            .where(ElementRef.owner_id == owner_id)
            .order_by(ElementRef.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_for_owners(self, owner_type: str, owner_ids: list[str]) -> dict[str, list[ElementRef]]:
        """Batch-load element refs for many owners (avoids an N+1 over a list page)."""
        grouped: dict[str, list[ElementRef]] = {oid: [] for oid in owner_ids}
        if not owner_ids:
            return grouped
        result = await self.session.execute(
            select(ElementRef)
            .where(ElementRef.owner_type == owner_type)
            .where(ElementRef.owner_id.in_(owner_ids))
            .order_by(ElementRef.created_at.asc())
        )
        for ref in result.scalars().all():
            grouped.setdefault(ref.owner_id, []).append(ref)
        return grouped

    async def delete_for_owner(self, owner_type: str, owner_id: str) -> None:
        for ref in await self.list_for_owner(owner_type, owner_id):
            await self.session.delete(ref)
        await self.session.flush()
