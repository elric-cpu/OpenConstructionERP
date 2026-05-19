# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Data access for the clash detection module."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bim_hub.models import BIMElement, BIMModel
from app.modules.clash.models import ClashResult, ClashRun


class ClashRepository:
    """‌⁠‍CRUD for clash runs/results + the BIM element feed for the engine."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── BIM element feed (broad-phase input) ───────────────────────────

    async def models_for_project(
        self, project_id: uuid.UUID
    ) -> list[BIMModel]:
        """‌⁠‍Every BIM model belonging to ``project_id`` (newest first)."""
        stmt = (
            select(BIMModel)
            .where(BIMModel.project_id == project_id)
            .order_by(BIMModel.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def elements_with_geometry(
        self, model_ids: list[uuid.UUID]
    ) -> list[BIMElement]:
        """Load every element of ``model_ids`` that carries a bounding box.

        Elements without geometry (annotations, schedules) can't clash, so
        they're filtered out at the query to keep the broad phase lean.
        """
        if not model_ids:
            return []
        stmt = select(BIMElement).where(
            BIMElement.model_id.in_(model_ids),
            BIMElement.bounding_box.is_not(None),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def categories_for_models(
        self, model_ids: list[uuid.UUID]
    ) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        """Distinct element_type and discipline facets (+ counts).

        Only counts elements that carry a bounding box — i.e. exactly the
        elements the clash broad phase will actually feed — so the Set A /
        Set B pickers never advertise a type that can't clash. Returns
        ``(element_types, disciplines)``, each a list of
        ``(value, count)`` sorted by count desc then value.
        """
        if not model_ids:
            return [], []

        async def _facet(col) -> list[tuple[str, int]]:
            stmt = (
                select(col, func.count())
                .where(
                    BIMElement.model_id.in_(model_ids),
                    BIMElement.bounding_box.is_not(None),
                    col.is_not(None),
                    col != "",
                )
                .group_by(col)
                .order_by(func.count().desc(), col)
            )
            return [
                (str(v), int(n))
                for v, n in (await self.session.execute(stmt)).all()
            ]

        return (
            await _facet(BIMElement.element_type),
            await _facet(BIMElement.discipline),
        )

    # ── ClashRun ───────────────────────────────────────────────────────

    def add_run(self, run: ClashRun) -> None:
        self.session.add(run)

    async def get_run(
        self, project_id: uuid.UUID, run_id: uuid.UUID
    ) -> ClashRun | None:
        stmt = select(ClashRun).where(
            ClashRun.id == run_id, ClashRun.project_id == project_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_runs(self, project_id: uuid.UUID) -> list[ClashRun]:
        stmt = (
            select(ClashRun)
            .where(ClashRun.project_id == project_id)
            .order_by(ClashRun.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_run(self, run: ClashRun) -> None:
        await self.session.delete(run)
        await self.session.flush()

    # ── ClashResult ────────────────────────────────────────────────────

    def add_results(self, results: list[ClashResult]) -> None:
        self.session.add_all(results)

    async def clear_results(self, run_id: uuid.UUID) -> None:
        """Wipe a run's results (re-run replaces, never appends)."""
        await self.session.execute(
            delete(ClashResult).where(ClashResult.run_id == run_id)
        )
        await self.session.flush()

    async def get_result(
        self, run_id: uuid.UUID, result_id: uuid.UUID
    ) -> ClashResult | None:
        stmt = select(ClashResult).where(
            ClashResult.id == result_id, ClashResult.run_id == run_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_results(
        self,
        run_id: uuid.UUID,
        *,
        status: str | None = None,
        clash_type: str | None = None,
        discipline: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[ClashResult], int]:
        base = select(ClashResult).where(ClashResult.run_id == run_id)
        if status:
            base = base.where(ClashResult.status == status)
        if clash_type:
            base = base.where(ClashResult.clash_type == clash_type)
        if discipline:
            base = base.where(
                (ClashResult.a_discipline == discipline)
                | (ClashResult.b_discipline == discipline)
            )
        total = (
            await self.session.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
        rows = (
            await self.session.execute(
                base.order_by(
                    ClashResult.clash_type,
                    ClashResult.penetration_m.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def results_for_export(
        self, run_id: uuid.UUID, result_ids: list[uuid.UUID] | None
    ) -> list[ClashResult]:
        """Resolve the export selection — explicit ids or all OPEN clashes."""
        stmt = select(ClashResult).where(ClashResult.run_id == run_id)
        if result_ids:
            stmt = stmt.where(ClashResult.id.in_(result_ids))
        else:
            stmt = stmt.where(
                ClashResult.status.in_(("new", "active", "reviewed"))
            )
        return list((await self.session.execute(stmt)).scalars().all())
