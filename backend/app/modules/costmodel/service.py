"""‌⁠‍5D Cost Model service — business logic for EVM, budgets, and cash flow.

Stateless service layer.  Handles:
- EVM snapshot creation and S-curve data
- Dashboard KPIs aggregation
- Budget generation from BOQ positions
- Cash flow generation from budget schedule
- Event publishing for inter-module communication
"""

import logging
import uuid
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.costmodel.models import (
    BudgetLine,
    CashFlow,
    ControlAccount,
    CostLine,
    CostSnapshot,
)
from app.modules.costmodel.repository import (
    BudgetLineRepository,
    CashFlowRepository,
    ControlAccountRepository,
    CostLineRepository,
    CostSpineRepository,
    SnapshotRepository,
)
from app.modules.costmodel.schemas import (
    BudgetCategoryRow,
    BudgetLineCreate,
    BudgetLineUpdate,
    BudgetSummary,
    CashFlowCreate,
    CashFlowData,
    CashFlowPeriod,
    ControlAccountCreate,
    ControlAccountResponse,
    ControlAccountUpdate,
    CostLineCreate,
    CostLineLinks,
    CostLineResponse,
    CostLineRollupResponse,
    CostLineUpdate,
    DashboardResponse,
    EVMResponse,
    SCurveData,
    SCurvePeriod,
    SnapshotCreate,
    SnapshotUpdate,
    SpineGenerationResult,
    SpineRollupResponse,
    WhatIfAdjustments,
    WhatIfResult,
)

_logger_ev = logging.getLogger(__name__ + ".events")


async def _safe_publish(name: str, data: dict, source_module: str = "") -> None:
    try:
        event_bus.publish_detached(name, data, source_module=source_module)
    except Exception:
        _logger_ev.debug("Event publish skipped: %s", name)


logger = logging.getLogger(__name__)


def _str_to_float(value: str | None) -> float:
    """‌⁠‍Convert a string-stored numeric value to float, defaulting to 0.0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _safe_divide(numerator: float, denominator: float) -> float:
    """‌⁠‍Safely divide two floats, returning 0.0 on zero denominator."""
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _variance_pct(planned: float, forecast: float) -> float:
    """Calculate variance percentage: (planned - forecast) / planned * 100."""
    if planned == 0.0:
        return 0.0
    return round((planned - forecast) / planned * 100.0, 2)


class CostModelService:
    """Business logic for 5D Cost Model operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.snapshot_repo = SnapshotRepository(session)
        self.budget_repo = BudgetLineRepository(session)
        self.cashflow_repo = CashFlowRepository(session)

    async def _get_project_currency(self, project_id: uuid.UUID) -> str:
        """Return the project's configured currency.

        Currency is strictly data-driven — it comes from the project record
        and nowhere else. When the project has no currency set (or the lookup
        fails) we return an empty string rather than fabricating a default;
        the UI is responsible for rendering a currency-less number instead of
        silently mislabelling, e.g., USD costs as EUR.
        """
        try:
            from app.modules.projects.repository import ProjectRepository

            repo = ProjectRepository(self.session)
            project = await repo.get_by_id(project_id)
            return project.currency if project and project.currency else ""
        except Exception:
            return ""

    # ── Snapshot operations ────────────────────────────────────────────────

    async def create_snapshot(self, data: SnapshotCreate) -> CostSnapshot:
        """Create a monthly EVM snapshot.

        Computes SPI and CPI from the provided planned/earned/actual values
        if they are not explicitly set.

        R5 audit (May 2026): ``(project_id, period)`` must be unique.
        Pre-audit two snapshots for the same period silently coexisted —
        ``get_latest_for_project`` then picked one arbitrarily and EVM
        rollups flapped between them. The DB-level unique index added in
        migration v3108 is the belt to this in-process suspenders.

        Args:
            data: Snapshot creation payload.

        Returns:
            The newly created snapshot.

        Raises:
            HTTPException: 409 if a snapshot already exists for
                ``(project_id, period)``.
        """
        # ── Duplicate-period guard (R5 audit) ────────────────────────────
        existing = await self.snapshot_repo.get_for_project_period(data.project_id, data.period)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Snapshot for period {data.period} already exists for "
                    "this project. Update the existing snapshot instead "
                    "(PATCH /5d/snapshots/{snapshot_id})."
                ),
            )

        spi = data.spi
        cpi = data.cpi

        # Auto-compute indices if not provided (left at default 0).
        # v3 §10 — money fields are Decimal; cast to float at this
        # boundary because SPI/CPI are unitless ratios stored as float.
        if spi == 0.0 and float(data.planned_cost) > 0.0:
            spi = round(
                _safe_divide(float(data.earned_value), float(data.planned_cost)),
                4,
            )
        if cpi == 0.0 and float(data.actual_cost) > 0.0:
            cpi = round(
                _safe_divide(float(data.earned_value), float(data.actual_cost)),
                4,
            )

        snapshot = CostSnapshot(
            project_id=data.project_id,
            period=data.period,
            planned_cost=str(data.planned_cost),
            earned_value=str(data.earned_value),
            actual_cost=str(data.actual_cost),
            forecast_eac=str(data.forecast_eac),
            spi=str(spi),
            cpi=str(cpi),
            notes=data.notes,
            metadata_=data.metadata,
        )
        snapshot = await self.snapshot_repo.create(snapshot)

        await _safe_publish(
            "costmodel.snapshot.created",
            {
                "snapshot_id": str(snapshot.id),
                "project_id": str(data.project_id),
                "period": data.period,
            },
            source_module="oe_costmodel",
        )

        logger.info(
            "EVM snapshot created: project=%s period=%s",
            data.project_id,
            data.period,
        )
        return snapshot

    async def get_snapshot(self, snapshot_id: uuid.UUID) -> CostSnapshot:
        """Get snapshot by ID. Raises 404 if not found."""
        snapshot = await self.snapshot_repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snapshot not found",
            )
        return snapshot

    async def list_snapshots(
        self,
        project_id: uuid.UUID,
        *,
        period_from: str | None = None,
        period_to: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[CostSnapshot], int]:
        """List EVM snapshots for a project with optional period range."""
        return await self.snapshot_repo.list_for_project(
            project_id,
            period_from=period_from,
            period_to=period_to,
            offset=offset,
            limit=limit,
        )

    async def update_snapshot(self, snapshot_id: uuid.UUID, data: SnapshotUpdate) -> CostSnapshot:
        """Update an EVM snapshot.

        Args:
            snapshot_id: Target snapshot identifier.
            data: Partial update payload.

        Returns:
            Updated snapshot.
        """
        await self.get_snapshot(snapshot_id)

        fields = data.model_dump(exclude_unset=True)

        # Convert float values to strings for storage
        for key in (
            "planned_cost",
            "earned_value",
            "actual_cost",
            "forecast_eac",
            "spi",
            "cpi",
        ):
            if key in fields:
                fields[key] = str(fields[key])

        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if fields:
            await self.snapshot_repo.update_fields(snapshot_id, **fields)

        updated = await self.snapshot_repo.get_by_id(snapshot_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snapshot not found after update",
            )
        return updated

    async def delete_snapshot(self, snapshot_id: uuid.UUID) -> None:
        """Delete an EVM cost snapshot. Raises 404 if not found.

        Emits a ``costmodel.snapshot.deleted`` event so downstream
        aggregates (portfolio dashboards, S-curve caches) can invalidate.
        """
        snapshot = await self.snapshot_repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snapshot not found",
            )

        project_id = str(snapshot.project_id)
        period = snapshot.period
        await self.snapshot_repo.delete(snapshot_id)

        await _safe_publish(
            "costmodel.snapshot.deleted",
            {
                "snapshot_id": str(snapshot_id),
                "project_id": project_id,
                "period": period,
            },
            source_module="oe_costmodel",
        )

        logger.info("EVM snapshot deleted: %s", snapshot_id)

    # ── Dashboard ──────────────────────────────────────────────────────────

    async def get_dashboard(self, project_id: uuid.UUID) -> DashboardResponse:
        """Aggregate all budget lines into summary KPIs.

        Computes total budget, committed, actual, forecast, variance,
        and pulls SPI/CPI from the latest EVM snapshot.

        Args:
            project_id: Target project.

        Returns:
            DashboardResponse with aggregated KPIs.
        """
        aggregates = await self.budget_repo.aggregate_by_project(project_id)

        total_budget = _str_to_float(aggregates["total_planned"])
        total_committed = _str_to_float(aggregates["total_committed"])
        total_actual = _str_to_float(aggregates["total_actual"])
        total_forecast = _str_to_float(aggregates["total_forecast"])
        variance = total_budget - total_forecast

        # Get SPI and CPI from latest snapshot
        spi = 0.0
        cpi = 0.0
        latest = await self.snapshot_repo.get_latest_for_project(project_id)
        if latest is not None:
            spi = _str_to_float(latest.spi)
            cpi = _str_to_float(latest.cpi)

        budget_status = "on_budget" if variance >= 0 else "over_budget"

        variance_pct = _variance_pct(total_budget, total_forecast) if total_budget > 0 else 0.0

        return DashboardResponse(
            total_budget=round(total_budget, 2),
            total_committed=round(total_committed, 2),
            total_actual=round(total_actual, 2),
            total_forecast=round(total_forecast, 2),
            variance=round(variance, 2),
            variance_pct=round(variance_pct, 2),
            spi=round(spi, 4),
            cpi=round(cpi, 4),
            status=budget_status,
            currency=await self._get_project_currency(project_id),
        )

    # ── S-Curve ────────────────────────────────────────────────────────────

    async def get_s_curve(self, project_id: uuid.UUID) -> SCurveData:
        """Build S-curve time series from EVM snapshots.

        Each snapshot stores the standard EVM measures BCWS/BCWP/ACWP
        (planned_cost / earned_value / actual_cost). By definition these are
        *cumulative-to-date* values, and every other consumer in this module
        (dashboard, EVM, what-if) treats them as absolute totals. The S-curve
        therefore plots the snapshot values directly — re-summing them across
        periods (the previous behaviour) double-counted and produced curves
        that climbed far past BAC.

        Snapshots are returned ``period`` ascending by the repository, so the
        series is already chronologically ordered.

        Args:
            project_id: Target project.

        Returns:
            SCurveData with list of period data points.
        """
        snapshots, _ = await self.snapshot_repo.list_for_project(project_id, limit=1000)

        periods: list[SCurvePeriod] = []
        for snap in snapshots:
            periods.append(
                SCurvePeriod(
                    period=snap.period,
                    planned=round(_str_to_float(snap.planned_cost), 2),
                    earned=round(_str_to_float(snap.earned_value), 2),
                    actual=round(_str_to_float(snap.actual_cost), 2),
                )
            )

        # Fallback: if no snapshots, build S-curve from cash flow data
        if not periods:
            cash_flows, _ = await self.cashflow_repo.list_for_project(project_id)
            seen: set[str] = set()
            for cf in cash_flows:
                if cf.period in seen:
                    continue
                seen.add(cf.period)
                periods.append(
                    SCurvePeriod(
                        period=cf.period,
                        planned=round(_str_to_float(cf.cumulative_planned), 2),
                        earned=0.0,
                        actual=round(_str_to_float(cf.cumulative_actual), 2),
                    )
                )

        return SCurveData(periods=periods)

    # ── Cash Flow ──────────────────────────────────────────────────────────

    async def get_cash_flow(self, project_id: uuid.UUID) -> CashFlowData:
        """Build monthly cash flow data from cash flow entries.

        Args:
            project_id: Target project.

        Returns:
            CashFlowData with list of period data points.
        """
        entries, _ = await self.cashflow_repo.list_for_project(project_id, limit=1000)

        periods: list[CashFlowPeriod] = []
        for entry in entries:
            inflow = _str_to_float(entry.actual_inflow) or _str_to_float(entry.planned_inflow)
            outflow = _str_to_float(entry.actual_outflow) or _str_to_float(entry.planned_outflow)

            periods.append(
                CashFlowPeriod(
                    period=entry.period,
                    inflow=round(inflow, 2),
                    outflow=round(outflow, 2),
                    cumulative_planned=round(_str_to_float(entry.cumulative_planned), 2),
                    cumulative_actual=round(_str_to_float(entry.cumulative_actual), 2),
                )
            )

        return CashFlowData(periods=periods)

    async def create_cash_flow_entry(self, data: CashFlowCreate) -> CashFlow:
        """Create a manual cash flow entry.

        Args:
            data: Cash flow creation payload.

        Returns:
            The newly created cash flow entry.
        """
        entry = CashFlow(
            project_id=data.project_id,
            period=data.period,
            category=data.category,
            planned_inflow=str(data.planned_inflow),
            planned_outflow=str(data.planned_outflow),
            actual_inflow=str(data.actual_inflow),
            actual_outflow=str(data.actual_outflow),
            cumulative_planned=str(data.cumulative_planned),
            cumulative_actual=str(data.cumulative_actual),
            metadata_=data.metadata,
        )
        entry = await self.cashflow_repo.create(entry)

        await _safe_publish(
            "costmodel.cashflow.created",
            {
                "entry_id": str(entry.id),
                "project_id": str(data.project_id),
                "period": data.period,
            },
            source_module="oe_costmodel",
        )

        logger.info(
            "Cash flow entry created: project=%s period=%s",
            data.project_id,
            data.period,
        )
        return entry

    # ── Budget operations ──────────────────────────────────────────────────

    async def get_budget_summary(self, project_id: uuid.UUID) -> BudgetSummary:
        """Group budget lines by category and compute per-category totals.

        Args:
            project_id: Target project.

        Returns:
            BudgetSummary with per-category breakdown.
        """
        rows = await self.budget_repo.aggregate_by_category(project_id)

        categories: list[BudgetCategoryRow] = []
        for row in rows:
            planned = _str_to_float(row["planned"])
            committed = _str_to_float(row["committed"])
            actual = _str_to_float(row["actual"])
            forecast = _str_to_float(row["forecast"])

            categories.append(
                BudgetCategoryRow(
                    category=row["category"],
                    planned=round(planned, 2),
                    committed=round(committed, 2),
                    actual=round(actual, 2),
                    forecast=round(forecast, 2),
                    variance=round(planned - forecast, 2),
                    variance_pct=_variance_pct(planned, forecast),
                )
            )

        return BudgetSummary(categories=categories)

    async def list_budget_lines(
        self,
        project_id: uuid.UUID,
        *,
        category: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> tuple[list[BudgetLine], int]:
        """List detailed budget lines for a project."""
        return await self.budget_repo.list_for_project(project_id, category=category, offset=offset, limit=limit)

    async def create_budget_line(self, data: BudgetLineCreate) -> BudgetLine:
        """Create a single budget line.

        Args:
            data: Budget line creation payload.

        Returns:
            The newly created budget line.
        """
        line = BudgetLine(
            project_id=data.project_id,
            boq_position_id=data.boq_position_id,
            activity_id=data.activity_id,
            category=data.category,
            description=data.description,
            planned_amount=str(data.planned_amount),
            committed_amount=str(data.committed_amount),
            actual_amount=str(data.actual_amount),
            forecast_amount=str(data.forecast_amount),
            period_start=data.period_start,
            period_end=data.period_end,
            currency=data.currency,
            metadata_=data.metadata,
        )
        line = await self.budget_repo.create(line)

        await _safe_publish(
            "costmodel.budget_line.created",
            {
                "line_id": str(line.id),
                "project_id": str(data.project_id),
                "category": data.category,
            },
            source_module="oe_costmodel",
        )

        logger.info(
            "Budget line created: project=%s category=%s",
            data.project_id,
            data.category,
        )
        return line

    async def update_budget_line(self, line_id: uuid.UUID, data: BudgetLineUpdate) -> BudgetLine:
        """Update committed, actual, forecast or other fields on a budget line.

        Args:
            line_id: Target budget line identifier.
            data: Partial update payload.

        Returns:
            Updated budget line.
        """
        line = await self.budget_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Budget line not found",
            )

        # Capture project_id before update_fields() calls expire_all(),
        # which would invalidate the ORM object and trigger a sync lazy-load
        # (MissingGreenlet) when accessing line.project_id afterwards.
        project_id_str = str(line.project_id)

        fields = data.model_dump(exclude_unset=True)

        # Convert float values to strings for storage
        for key in ("planned_amount", "committed_amount", "actual_amount", "forecast_amount"):
            if key in fields:
                fields[key] = str(fields[key])

        # Convert GUID fields to string for storage
        for key in ("boq_position_id", "activity_id"):
            if key in fields and fields[key] is not None:
                fields[key] = fields[key]  # GUID type handles conversion

        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if fields:
            await self.budget_repo.update_fields(line_id, **fields)

            await _safe_publish(
                "costmodel.budget_line.updated",
                {
                    "line_id": str(line_id),
                    "project_id": project_id_str,
                    "fields": list(fields.keys()),
                },
                source_module="oe_costmodel",
            )

        updated = await self.budget_repo.get_by_id(line_id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Budget line not found after update",
            )
        return updated

    async def delete_budget_line(self, line_id: uuid.UUID) -> None:
        """Delete a budget line. Raises 404 if not found."""
        line = await self.budget_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Budget line not found",
            )

        project_id = str(line.project_id)
        await self.budget_repo.delete(line_id)

        await _safe_publish(
            "costmodel.budget_line.deleted",
            {"line_id": str(line_id), "project_id": project_id},
            source_module="oe_costmodel",
        )

        logger.info("Budget line deleted: %s", line_id)

    # ── EVM Calculations ──────────────────────────────────────────────────

    async def calculate_evm(self, project_id: uuid.UUID) -> EVMResponse:
        """Calculate real Earned Value Management metrics from schedule progress and budget.

        Reads schedule activities for progress percentage and budget lines for planned
        and actual values.  Computes all standard EVM indices.

        Algorithm:
            1. BAC = sum of planned_amount across all budget lines
            2. AC  = sum of actual_amount across all budget lines
            3. time_elapsed% = computed from project schedule start/end vs today
            4. schedule_progress% = weighted average of activity progress_pct
               (weighted by planned_amount of linked budget lines)
            5. PV  = BAC * time_elapsed%
            6. EV  = BAC * schedule_progress%
            7. Derived indices: SV, CV, SPI, CPI, EAC, ETC, VAC, TCPI

        Known limitation (v1.3.x):
            PV is an approximation: ``BAC × time_elapsed%`` rather than a proper
            time-phased baseline. When a project has not started yet (``time_elapsed%``
            ~ 0) but activities already report progress, SPI = EV / PV explodes.
            To prevent mathematically impossible values we clamp:
                - ``pv`` to a minimum of ``1% × BAC`` (avoids divide-by-near-zero)
                - ``spi`` to the ``[0.0, 5.0]`` range
            and set ``spi_capped=True`` so the UI can label the figure as approximate.
            TODO (v1.4): replace with a proper time-phased PV computed from
            ``BudgetLine`` + ``Activity`` planned dates (see audit notes, Option A).

        Args:
            project_id: Target project.

        Returns:
            EVMResponse with all computed EVM metrics.
        """
        from datetime import date

        from app.modules.schedule.repository import ActivityRepository, ScheduleRepository

        # ── Step 1: Aggregate budget totals ────────────────────────────────
        aggregates = await self.budget_repo.aggregate_by_project(project_id)
        bac = _str_to_float(aggregates["total_planned"])
        ac = _str_to_float(aggregates["total_actual"])

        if bac == 0.0:
            return EVMResponse(
                bac=0.0,
                ac=ac,
                status="unknown",
            )

        # ── Step 2: Read schedule activities for progress ──────────────────
        schedule_repo = ScheduleRepository(self.session)
        schedules, _ = await schedule_repo.list_for_project(project_id, limit=50)

        time_elapsed_pct = 0.0
        schedule_progress_pct = 0.0
        # Tracks whether we actually have a usable schedule signal. When False,
        # we surface this to the caller via evm_status="schedule_unknown"
        # instead of silently falling back to a 50 % placeholder — the legacy
        # fallback skewed portfolio-level reports by pretending half-elapsed
        # progress on projects that had no schedule at all.
        schedule_known = False

        if schedules:
            # Use the first (primary) schedule for time elapsed calculation
            primary_schedule = schedules[0]
            today = date.today()

            # Compute time_elapsed_pct from schedule dates
            if primary_schedule.start_date and primary_schedule.end_date:
                try:
                    start = date.fromisoformat(primary_schedule.start_date[:10])
                    end = date.fromisoformat(primary_schedule.end_date[:10])
                    total_days = (end - start).days
                    if total_days > 0:
                        elapsed_days = (today - start).days
                        time_elapsed_pct = max(0.0, min(100.0, (elapsed_days / total_days) * 100.0))
                        schedule_known = True
                except (ValueError, TypeError) as exc:
                    # Log explicitly instead of swallowing silently. Bad schedule
                    # dates are a data-quality issue worth surfacing to ops —
                    # previously this bug masqueraded as "on track" projects.
                    logger.warning(
                        "Unparseable schedule dates on schedule_id=%s (start=%r, end=%r): %s",
                        getattr(primary_schedule, "id", "<unknown>"),
                        primary_schedule.start_date,
                        primary_schedule.end_date,
                        exc,
                    )

            # Compute weighted schedule progress from all activities
            activity_repo = ActivityRepository(self.session)
            total_weighted_progress = 0.0
            total_weight = 0.0

            # Build lookup: budget lines keyed by activity_id (hoisted out of the
            # per-schedule loop — these lines are project-scoped, not schedule-scoped,
            # so fetching once avoids an N+1 query).
            budget_lines, _ = await self.budget_repo.list_for_project(project_id, limit=10000)
            activity_budget: dict[str, float] = {}
            for bl in budget_lines:
                if bl.activity_id is not None:
                    aid = str(bl.activity_id)
                    activity_budget[aid] = activity_budget.get(aid, 0.0) + _str_to_float(bl.planned_amount)

            for schedule in schedules:
                activities, _ = await activity_repo.list_for_schedule(schedule.id, limit=10000)

                for act in activities:
                    act_id = str(act.id)
                    progress = _str_to_float(act.progress_pct)

                    # Weight by the planned budget linked to this activity,
                    # fallback to equal weight if no budget link exists
                    weight = activity_budget.get(act_id, 0.0)
                    if weight == 0.0:
                        # Use equal weight for unlinked activities
                        weight = 1.0

                    total_weighted_progress += weight * progress
                    total_weight += weight

            if total_weight > 0.0:
                schedule_progress_pct = total_weighted_progress / total_weight
        else:
            # No schedule at all — try the latest snapshot as a weak signal,
            # but do NOT fake a 50 % time_elapsed. The old 50 % placeholder
            # silently labelled unscheduled projects as "half-elapsed",
            # which skewed portfolio roll-ups and made at-risk projects look
            # on-track. Instead we leave time_elapsed_pct at 0 and mark
            # evm_status="schedule_unknown" further down so the UI/API caller
            # can tell there is genuinely no schedule data.
            latest = await self.snapshot_repo.get_latest_for_project(project_id)
            if latest is not None:
                pv_snap = _str_to_float(latest.planned_cost)
                ev_snap = _str_to_float(latest.earned_value)
                if pv_snap > 0.0:
                    schedule_progress_pct = (ev_snap / bac) * 100.0

        # ── Step 3: Compute EVM values ─────────────────────────────────────
        # PV is an approximation (BAC × time_elapsed%). See the function
        # docstring for limitations. We clamp PV to a minimum of 1% × BAC so
        # SPI never explodes toward infinity when the project has not really
        # started yet but activities report nominal progress.
        raw_pv = bac * (time_elapsed_pct / 100.0)
        pv_floor = bac * 0.01  # 1% of BAC — prevents divide-by-near-zero
        pv = max(raw_pv, pv_floor)
        ev = bac * (schedule_progress_pct / 100.0)

        sv = ev - pv
        cv = ev - ac
        raw_spi = _safe_divide(ev, pv)
        # Clamp SPI into the [0, 5] band. Anything above 5 is almost certainly
        # the PV proxy being unreliable (project hasn't actually started yet).
        spi_capped = raw_spi > 5.0 or raw_spi < 0.0 or raw_pv < pv_floor
        spi = min(max(raw_spi, 0.0), 5.0)
        cpi = _safe_divide(ev, ac)
        eac = _safe_divide(bac, cpi) if cpi != 0.0 else bac
        etc = max(0.0, eac - ac)
        vac = bac - eac
        # TCPI is mathematically undefined when (BAC - AC) <= 0: the
        # project is at-or-over budget so "work remaining vs cash
        # remaining" has no finite answer. Pre-audit this returned 0.0
        # via _safe_divide, which dashboards mis-rendered as "perfect
        # efficiency required". Surface None so the UI can label N/A.
        tcpi: float | None
        remaining_budget = bac - ac
        if remaining_budget <= 0.0:
            tcpi = None
        else:
            tcpi = (bac - ev) / remaining_budget

        # ── Step 4: Determine project health status ────────────────────────
        # When we have no schedule signal at all, any SPI-based classification
        # is meaningless (see `schedule_known` comment above). Surface a
        # distinct sentinel so dashboards can render "no schedule data" rather
        # than a misleading "on track"/"at risk" badge.
        if not schedule_known:
            evm_status = "schedule_unknown"
        elif spi >= 0.95 and cpi >= 0.95:
            evm_status = "on_track"
        elif spi >= 0.85 and cpi >= 0.85:
            evm_status = "at_risk"
        elif spi > 0.0 or cpi > 0.0:
            evm_status = "critical"
        else:
            evm_status = "unknown"

        logger.info(
            "EVM calculated: project=%s BAC=%.2f PV=%.2f EV=%.2f AC=%.2f SPI=%.4f CPI=%.4f",
            project_id,
            bac,
            pv,
            ev,
            ac,
            spi,
            cpi,
        )

        return EVMResponse(
            bac=round(bac, 2),
            pv=round(pv, 2),
            ev=round(ev, 2),
            ac=round(ac, 2),
            sv=round(sv, 2),
            cv=round(cv, 2),
            spi=round(spi, 4),
            cpi=round(cpi, 4),
            eac=round(eac, 2),
            etc=round(etc, 2),
            vac=round(vac, 2),
            tcpi=round(tcpi, 4) if tcpi is not None else None,
            time_elapsed_pct=round(time_elapsed_pct, 2),
            schedule_progress_pct=round(schedule_progress_pct, 2),
            status=evm_status,
            spi_capped=spi_capped,
        )

    # ── What-If Scenarios ─────────────────────────────────────────────────

    async def create_what_if_scenario(
        self,
        project_id: uuid.UUID,
        adjustments: WhatIfAdjustments,
    ) -> WhatIfResult:
        """Create a what-if scenario by cloning the current budget as a snapshot.

        Applies percentage-based adjustments to material and labor cost categories,
        and optionally adjusts duration impact on forecast.

        Algorithm:
            1. Calculate current EVM as baseline
            2. Compute adjusted BAC by applying category-level adjustments
            3. Compute adjusted EAC using the current CPI against adjusted BAC
            4. Create a snapshot recording the scenario
            5. Return comparison of original vs adjusted values

        Args:
            project_id: Target project.
            adjustments: Scenario name and percentage adjustments.

        Returns:
            WhatIfResult with original and adjusted values plus snapshot reference.
        """
        # ── Step 1: Get current EVM baseline ───────────────────────────────
        evm = await self.calculate_evm(project_id)

        # ── Step 2: Get budget breakdown by category ───────────────────────
        budget_rows = await self.budget_repo.aggregate_by_category(project_id)

        original_bac = evm.bac
        adjusted_bac = 0.0

        for row in budget_rows:
            category = row["category"]
            planned = _str_to_float(row["planned"])

            # Apply category-specific adjustment
            if category == "material":
                factor = 1.0 + (adjustments.material_cost_pct / 100.0)
            elif category == "labor":
                factor = 1.0 + (adjustments.labor_cost_pct / 100.0)
            else:
                factor = 1.0

            adjusted_bac += planned * factor

        # ── Step 3: Apply duration adjustment to indirect/time-dependent costs
        # Duration change affects overhead proportionally
        if adjustments.duration_pct != 0.0:
            duration_factor = 1.0 + (adjustments.duration_pct / 100.0)
            for row in budget_rows:
                if row["category"] in ("overhead", "contingency"):
                    planned = _str_to_float(row["planned"])
                    # Add the delta from duration change (already counted at 1x above)
                    adjusted_bac += planned * (duration_factor - 1.0)

        # ── Step 4: Compute adjusted EAC using current CPI ────────────────
        cpi = evm.cpi if evm.cpi > 0.0 else 1.0
        adjusted_eac = _safe_divide(adjusted_bac, cpi)
        original_eac = evm.eac if evm.eac > 0.0 else original_bac
        delta = adjusted_eac - original_eac
        delta_pct = _variance_pct(original_eac, adjusted_eac) * -1.0 if original_eac > 0.0 else 0.0

        # ── Step 5: Create a snapshot recording the scenario ───────────────
        # Scenarios use a 'wif:<short-id>:YYYY-MM' period so the unique
        # (project_id, period) index added in v3108 cannot reject a
        # legitimate what-if just because the real monthly snapshot also
        # exists for this calendar month.
        from datetime import date

        today = date.today()
        period = f"wif:{uuid.uuid4().hex[:8]}:{today.year:04d}-{today.month:02d}"

        snapshot = CostSnapshot(
            project_id=project_id,
            period=period,
            planned_cost=str(round(adjusted_bac, 2)),
            earned_value=str(round(evm.ev, 2)),
            actual_cost=str(round(evm.ac, 2)),
            forecast_eac=str(round(adjusted_eac, 2)),
            spi=str(round(evm.spi, 4)),
            cpi=str(round(evm.cpi, 4)),
            notes=f"What-if scenario: {adjustments.name}",
            metadata_={
                "scenario": True,
                "scenario_name": adjustments.name,
                "adjustments": {
                    "material_cost_pct": adjustments.material_cost_pct,
                    "labor_cost_pct": adjustments.labor_cost_pct,
                    "duration_pct": adjustments.duration_pct,
                },
                "original_bac": round(original_bac, 2),
                "adjusted_bac": round(adjusted_bac, 2),
            },
        )
        snapshot = await self.snapshot_repo.create(snapshot)

        await _safe_publish(
            "costmodel.whatif.created",
            {
                "snapshot_id": str(snapshot.id),
                "project_id": str(project_id),
                "scenario_name": adjustments.name,
            },
            source_module="oe_costmodel",
        )

        logger.info(
            "What-if scenario created: project=%s name='%s' BAC=%.2f→%.2f EAC=%.2f→%.2f",
            project_id,
            adjustments.name,
            original_bac,
            adjusted_bac,
            original_eac,
            adjusted_eac,
        )

        return WhatIfResult(
            scenario_name=adjustments.name,
            original_bac=round(original_bac, 2),
            adjusted_bac=round(adjusted_bac, 2),
            original_eac=round(original_eac, 2),
            adjusted_eac=round(adjusted_eac, 2),
            delta=round(delta, 2),
            delta_pct=round(delta_pct, 2),
            adjustments_applied={
                "material_cost_pct": adjustments.material_cost_pct,
                "labor_cost_pct": adjustments.labor_cost_pct,
                "duration_pct": adjustments.duration_pct,
            },
            snapshot_id=snapshot.id,
        )

    # ── Generation helpers ─────────────────────────────────────────────────

    async def pick_default_boq(self, project_id: uuid.UUID) -> uuid.UUID | None:
        """Find the largest BOQ for a project (used when caller omits boq_id).

        Returns the BOQ id with the most positions, or None if the project
        has no BOQs.
        """
        from app.modules.boq.repository import BOQRepository

        boq_repo = BOQRepository(self.session)
        boqs, _ = await boq_repo.list_for_project(project_id, limit=100)
        if not boqs:
            return None
        # Pick the most recently updated BOQ — that's the one the user is
        # actively working on. position_count is computed lazily so don't
        # rely on it here.
        sorted_boqs = sorted(boqs, key=lambda b: b.updated_at, reverse=True)
        return sorted_boqs[0].id

    async def generate_budget_from_boq(self, project_id: uuid.UUID, boq_id: uuid.UUID) -> list[BudgetLine]:
        """Auto-generate budget lines from BOQ positions.

        Each BOQ position becomes a budget line with planned_amount = position total.
        Existing budget lines for the project are NOT deleted — new lines are appended.

        Idempotency (R5 audit, May 2026):
            Positions already wired to a budget line for this project are
            skipped. Re-running the endpoint after editing the BOQ creates
            lines only for the *new* positions. Pre-audit each call appended
            a fresh duplicate row per position, silently doubling BAC and
            poisoning every downstream EVM rollup.

        Args:
            project_id: Target project.
            boq_id: Source BOQ to generate budget from.

        Returns:
            List of newly created budget lines (empty if every position is
            already represented).
        """
        from app.modules.boq.repository import PositionRepository

        position_repo = PositionRepository(self.session)
        positions, _ = await position_repo.list_for_boq(boq_id, limit=10000)

        if not positions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No positions found in the specified BOQ",
            )

        # ── Idempotency guard ────────────────────────────────────────────
        # Skip positions that already have a budget line for this project.
        # This makes the endpoint safe to re-run after a BOQ edit; the
        # DB-level unique index added in the same migration is the belt to
        # this in-process suspenders.
        existing = await self.budget_repo.existing_position_ids(project_id)

        lines: list[BudgetLine] = []
        for pos in positions:
            if pos.id in existing:
                continue
            total = _str_to_float(pos.total)
            line = BudgetLine(
                project_id=project_id,
                boq_position_id=pos.id,
                category="material",  # Default; user can reclassify later
                description=f"{pos.ordinal} — {pos.description[:200]}",
                planned_amount=str(total),
                committed_amount="0",
                actual_amount="0",
                forecast_amount=str(total),
                currency="",
            )
            lines.append(line)

        if not lines:
            logger.info(
                "generate_budget_from_boq: every BOQ position already wired (project=%s boq=%s); no-op.",
                project_id,
                boq_id,
            )
            return []

        created = await self.budget_repo.bulk_create(lines)

        await _safe_publish(
            "costmodel.budget.generated",
            {
                "project_id": str(project_id),
                "boq_id": str(boq_id),
                "lines_created": len(created),
            },
            source_module="oe_costmodel",
        )

        logger.info(
            "Generated %d budget lines from BOQ %s for project %s",
            len(created),
            boq_id,
            project_id,
        )
        return created

    async def generate_cash_flow_from_schedule(self, project_id: uuid.UUID) -> list[CashFlow]:
        """Generate cash flow entries by spreading budget line amounts across their schedule.

        For budget lines that have period_start and period_end, the planned_amount
        is evenly distributed across the months in that range.  Lines without a
        schedule are placed into a single 'unscheduled' entry.

        Currency handling (R5 audit, May 2026): every line is converted to
        the project base currency via ``fx_rates`` before being added to
        the period bucket. Pre-audit cash flow totals silently mixed USD,
        EUR, JPY values into one ``Decimal`` and the S-curve plotted the
        result as if they were all base — a 100 % bug for any multi-
        currency project.

        Args:
            project_id: Target project.

        Returns:
            List of newly created cash flow entries.
        """
        budget_lines, _ = await self.budget_repo.list_for_project(project_id, limit=10000)

        if not budget_lines:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No budget lines found for the project",
            )

        # FX context for currency conversion below.
        base_currency, fx_map = await self.budget_repo._project_fx_context(project_id)

        # Aggregate outflows per period (Decimal end-to-end, base currency)
        from app.modules.costmodel.repository import _amount_in_base

        period_outflows: dict[str, Decimal] = {}

        for bl in budget_lines:
            line_ccy = (bl.currency or "").strip().upper()
            amount = _amount_in_base(bl.planned_amount, line_ccy, base_currency, fx_map)
            if amount == 0:
                continue

            start = bl.period_start
            end = bl.period_end

            if start and end and len(start) >= 7 and len(end) >= 7:
                # Spread evenly across months
                months = _month_range(start[:7], end[:7])
                if months:
                    per_month = amount / len(months)
                    for m in months:
                        period_outflows[m] = period_outflows.get(m, Decimal("0")) + per_month
                else:
                    # Fallback: single period
                    p = start[:7]
                    period_outflows[p] = period_outflows.get(p, Decimal("0")) + amount
            else:
                # No schedule — use a generic unscheduled bucket.
                # Keep the sentinel <= 10 chars to fit the period column (varchar(10)).
                period_outflows["unsched"] = period_outflows.get("unsched", Decimal("0")) + amount

        # Build cash flow entries with running cumulative
        entries: list[CashFlow] = []
        cumulative = Decimal("0")

        for period in sorted(period_outflows.keys()):
            outflow = period_outflows[period]
            cumulative += outflow

            entry = CashFlow(
                project_id=project_id,
                period=period,
                category="total",
                planned_inflow="0",
                planned_outflow=str(round(float(outflow), 2)),
                actual_inflow="0",
                actual_outflow="0",
                cumulative_planned=str(round(float(cumulative), 2)),
                cumulative_actual="0",
            )
            entries.append(entry)

        created = await self.cashflow_repo.bulk_create(entries)

        await _safe_publish(
            "costmodel.cashflow.generated",
            {
                "project_id": str(project_id),
                "entries_created": len(created),
            },
            source_module="oe_costmodel",
        )

        logger.info(
            "Generated %d cash flow entries for project %s",
            len(created),
            project_id,
        )
        return created

    # ── Project Intelligence (RFC 25) ──────────────────────────────────────

    async def get_variance(self, project_id: uuid.UUID):
        """Compute the budget-variance KPI for the Estimation Dashboard.

        Budget is ``sum(unit_rate * quantity)`` across all positions of the
        largest BOQ for the project — there is no dedicated ``baseline_total``
        column in the Position model today, so the current rate is used as
        the baseline. ``current`` is the live ``sum(total)``; any manual
        overrides (totals that diverge from quantity * rate) therefore
        surface as variance.

        Empty projects return zeros and a neutral ``red_line`` of 5.0%.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.modules.boq.models import BOQ
        from app.modules.costmodel.schemas import VarianceResponse

        stmt = (
            select(BOQ)
            .options(selectinload(BOQ.positions))
            .where(BOQ.project_id == project_id)
            .order_by(BOQ.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        boqs = list(result.scalars().all())

        currency = await self._get_project_currency(project_id)

        if not boqs:
            return VarianceResponse(currency=currency)

        # Aggregate across every BOQ for the project — estimators usually
        # work in one BOQ, but summing protects us when multiple revisions
        # exist and all contribute to the live cost signal.
        budget = 0.0
        current = 0.0
        for boq in boqs:
            for pos in boq.positions:
                # Skip section headers (empty unit)
                if not pos.unit:
                    continue
                qty = _str_to_float(pos.quantity)
                rate = _str_to_float(pos.unit_rate)
                total = _str_to_float(pos.total)
                budget += qty * rate
                current += total

        variance_abs = round(current - budget, 2)
        variance_pct = round((current - budget) / budget * 100, 2) if budget > 0 else 0.0

        return VarianceResponse(
            budget=round(budget, 2),
            current=round(current, 2),
            variance_abs=variance_abs,
            variance_pct=variance_pct,
            red_line=5.0,
            currency=currency,
        )


def _month_range(start: str, end: str) -> list[str]:
    """Generate list of YYYY-MM strings from start to end (inclusive).

    Args:
        start: Start period in YYYY-MM format.
        end: End period in YYYY-MM format.

    Returns:
        List of YYYY-MM strings.
    """
    try:
        sy, sm = int(start[:4]), int(start[5:7])
        ey, em = int(end[:4]), int(end[5:7])
    except (ValueError, IndexError):
        return []

    months: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
        # Safety: cap at 120 months (10 years) to prevent runaway
        if len(months) > 120:
            break

    return months


# ── Cost Spine service (v6.4) ─────────────────────────────────────────────────


def _control_account_to_response(account: ControlAccount) -> ControlAccountResponse:
    """Convert a ControlAccount ORM row to its response schema."""
    return ControlAccountResponse.model_validate(account)


def _cost_line_to_response(line: CostLine) -> CostLineResponse:
    """Convert a CostLine ORM row to its response schema, money as Decimal."""
    return CostLineResponse(
        id=line.id,
        project_id=line.project_id,
        control_account_id=line.control_account_id,
        code=line.code,
        description=line.description,
        unit=line.unit,
        source=line.source,
        boq_position_id=line.boq_position_id,
        boq_id=line.boq_id,
        estimate_quantity=Decimal(str(line.estimate_quantity or "0")),
        estimate_unit_rate=Decimal(str(line.estimate_unit_rate or "0")),
        estimate_amount=Decimal(str(line.estimate_amount or "0")),
        currency=line.currency,
        status=line.status,
        metadata_=line.metadata_,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def _account_code_from_classification(classification: object, standard: str) -> tuple[str, str] | None:
    """Derive ``(code, name)`` for a control account from a position classification.

    ``classification`` is the BOQ position JSONB, e.g.
    ``{"din276": "330", "masterformat": "04 20 00"}``. We pick the value for the
    requested ``standard`` (falling back to the first present standard) and use
    it as both the account code and a human label. Returns None when the
    position carries no usable classification so the caller can skip building an
    account for it.
    """
    if not isinstance(classification, dict) or not classification:
        return None
    # Prefer the configured standard, else the first non-empty entry.
    code = None
    if standard:
        raw = classification.get(standard)
        if raw not in (None, ""):
            code = str(raw).strip()
    if code is None:
        for value in classification.values():
            if value not in (None, ""):
                code = str(value).strip()
                break
    if not code:
        return None
    return code, code


class CostSpineService:
    """Business logic for the Cost Spine: control accounts, cost lines, rollups.

    Owns its own repositories and reuses the existing project-currency and
    event-publish helpers so FX and event semantics stay identical to the rest
    of the cost-model module.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.account_repo = ControlAccountRepository(session)
        self.line_repo = CostLineRepository(session)
        self.spine_repo = CostSpineRepository(session)
        self.budget_repo = BudgetLineRepository(session)
        # Reuse CostModelService helpers (project currency, default BOQ pick).
        self._cost_service = CostModelService(session)

    async def _get_project_currency(self, project_id: uuid.UUID) -> str:
        return await self._cost_service._get_project_currency(project_id)

    # ── Control accounts ────────────────────────────────────────────────────

    async def list_accounts(self, project_id: uuid.UUID) -> list[ControlAccountResponse]:
        """Return the project's control accounts as a tree-ordered list."""
        accounts = await self.account_repo.list_for_project(project_id)
        return [_control_account_to_response(a) for a in accounts]

    async def create_account(self, data: ControlAccountCreate) -> ControlAccountResponse:
        """Create a control account, rejecting a duplicate project+code (409)."""
        if data.project_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id is required")
        existing = await self.account_repo.get_by_project_code(data.project_id, data.code)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Control account code '{data.code}' already exists in this project.",
            )
        if data.parent_id is not None:
            parent = await self.account_repo.get_by_id(data.parent_id)
            if parent is None or parent.project_id != data.project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="parent_id does not reference a control account in this project.",
                )
        account = ControlAccount(
            project_id=data.project_id,
            parent_id=data.parent_id,
            code=data.code,
            name=data.name,
            classification_standard=data.classification_standard,
            status=data.status,
            sort_order=data.sort_order,
            metadata_=data.metadata,
        )
        account = await self.account_repo.create(account)
        await _safe_publish(
            "costmodel.spine.account_created",
            {"account_id": str(account.id), "project_id": str(data.project_id), "code": data.code},
            source_module="oe_costmodel",
        )
        return _control_account_to_response(account)

    async def update_account(self, account_id: uuid.UUID, data: ControlAccountUpdate) -> ControlAccountResponse:
        """Update a control account. Raises 404 if missing, 409 on code clash."""
        account = await self.account_repo.get_by_id(account_id)
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control account not found")

        project_id = account.project_id
        fields = data.model_dump(exclude_unset=True)

        if "code" in fields and fields["code"] != account.code:
            clash = await self.account_repo.get_by_project_code(project_id, fields["code"])
            if clash is not None and clash.id != account_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Control account code '{fields['code']}' already exists in this project.",
                )
        if fields.get("parent_id") is not None:
            if fields["parent_id"] == account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A control account cannot be its own parent.",
                )
            parent = await self.account_repo.get_by_id(fields["parent_id"])
            if parent is None or parent.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="parent_id does not reference a control account in this project.",
                )
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if fields:
            await self.account_repo.update_fields(account_id, **fields)
        updated = await self.account_repo.get_by_id(account_id)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control account not found after update")
        return _control_account_to_response(updated)

    async def delete_account(self, account_id: uuid.UUID) -> None:
        """Delete a control account. Raises 404 if missing, 409 if lines reference it."""
        account = await self.account_repo.get_by_id(account_id)
        if account is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control account not found")
        referencing = await self.account_repo.count_lines_referencing(account_id)
        if referencing > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Control account is referenced by {referencing} cost line(s). "
                    "Reassign or delete those lines first."
                ),
            )
        project_id = str(account.project_id)
        await self.account_repo.delete(account_id)
        await _safe_publish(
            "costmodel.spine.account_deleted",
            {"account_id": str(account_id), "project_id": project_id},
            source_module="oe_costmodel",
        )

    # ── Cost lines ──────────────────────────────────────────────────────────

    async def list_lines(
        self,
        project_id: uuid.UUID,
        *,
        control_account_id: uuid.UUID | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[CostLineResponse]:
        """List cost lines for a project with optional account/status filters."""
        lines, _ = await self.line_repo.list_for_project(
            project_id,
            control_account_id=control_account_id,
            status=status,
            offset=offset,
            limit=limit,
        )
        return [_cost_line_to_response(line) for line in lines]

    async def create_line(self, data: CostLineCreate) -> CostLineResponse:
        """Create a cost line, auto-generating a code when omitted (409 on clash)."""
        if data.project_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id is required")

        code = (data.code or "").strip() or f"CL-{uuid.uuid4().hex[:8].upper()}"
        existing = await self.line_repo.get_by_project_code(data.project_id, code)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cost line code '{code}' already exists in this project.",
            )
        if data.control_account_id is not None:
            account = await self.account_repo.get_by_id(data.control_account_id)
            if account is None or account.project_id != data.project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="control_account_id does not reference a control account in this project.",
                )
        currency = data.currency or await self._get_project_currency(data.project_id)
        line = CostLine(
            project_id=data.project_id,
            control_account_id=data.control_account_id,
            code=code,
            description=data.description,
            unit=data.unit,
            source=data.source,
            boq_position_id=data.boq_position_id,
            boq_id=data.boq_id,
            estimate_quantity=str(data.estimate_quantity),
            estimate_unit_rate=str(data.estimate_unit_rate),
            estimate_amount=str(data.estimate_amount),
            currency=currency,
            status=data.status,
            metadata_=data.metadata,
        )
        line = await self.line_repo.create(line)
        await _safe_publish(
            "costmodel.spine.cost_line_created",
            {"cost_line_id": str(line.id), "project_id": str(data.project_id), "code": code},
            source_module="oe_costmodel",
        )
        return _cost_line_to_response(line)

    async def update_line(self, line_id: uuid.UUID, data: CostLineUpdate) -> CostLineResponse:
        """Update a cost line. Raises 404 if missing, 409 on code clash."""
        line = await self.line_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost line not found")

        project_id = line.project_id
        fields = data.model_dump(exclude_unset=True)

        if "code" in fields and fields["code"] != line.code:
            clash = await self.line_repo.get_by_project_code(project_id, fields["code"])
            if clash is not None and clash.id != line_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cost line code '{fields['code']}' already exists in this project.",
                )
        if fields.get("control_account_id") is not None:
            account = await self.account_repo.get_by_id(fields["control_account_id"])
            if account is None or account.project_id != project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="control_account_id does not reference a control account in this project.",
                )
        for key in ("estimate_quantity", "estimate_unit_rate", "estimate_amount"):
            if key in fields and fields[key] is not None:
                fields[key] = str(fields[key])
        if "metadata" in fields:
            fields["metadata_"] = fields.pop("metadata")

        if fields:
            await self.line_repo.update_fields(line_id, **fields)
        updated = await self.line_repo.get_by_id(line_id)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost line not found after update")
        return _cost_line_to_response(updated)

    async def delete_line(self, line_id: uuid.UUID) -> None:
        """Delete a cost line. Raises 404 if missing, 409 if anything links to it."""
        line = await self.line_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost line not found")

        project_id = str(line.project_id)
        counts = await self._linked_counts(line_id, line.project_id)
        total_links = sum(counts.values())
        if total_links > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Cost line is still linked to downstream records. Unlink them first.",
                    "linked": counts,
                },
            )
        await self.line_repo.delete(line_id)
        await _safe_publish(
            "costmodel.spine.cost_line_deleted",
            {"cost_line_id": str(line_id), "project_id": project_id},
            source_module="oe_costmodel",
        )

    async def _linked_counts(self, line_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, int]:
        """Count downstream rows linked to a cost line (for delete-guard 409)."""
        from sqlalchemy import func, select

        from app.modules.boq.models import Position
        from app.modules.contracts.models import ContractLine
        from app.modules.procurement.models import MaterialRequisitionItem, PurchaseOrderItem

        async def _count(stmt: object) -> int:
            return (await self.session.execute(stmt)).scalar_one()

        budget = await _count(select(func.count()).where(BudgetLine.cost_line_id == line_id))
        positions = await _count(select(func.count()).where(Position.cost_line_id == line_id))
        po_items = await _count(select(func.count()).where(PurchaseOrderItem.cost_line_id == line_id))
        req_items = await _count(select(func.count()).where(MaterialRequisitionItem.cost_line_id == line_id))
        contract_lines = await _count(select(func.count()).where(ContractLine.cost_line_id == line_id))
        return {
            "budget_lines": budget,
            "boq_positions": positions,
            "po_items": po_items,
            "req_items": req_items,
            "contract_lines": contract_lines,
        }

    # ── Generation from BOQ ─────────────────────────────────────────────────

    async def generate_from_boq(
        self,
        project_id: uuid.UUID,
        boq_id: uuid.UUID | None = None,
    ) -> SpineGenerationResult:
        """Build the cost spine from a BOQ (idempotent, fill-nulls-only).

        Resolves the BOQ (largest/most-recent when ``boq_id`` is omitted), loads
        its positions, builds a control-account tree from each position's
        classification, upserts one cost line per position keyed on
        ``(project_id, code)`` (code from ``reference_code`` or an auto
        ``CL-XXXXXXXX``), captures the estimate quantity/rate/amount, inherits
        the project currency, writes ``cost_line_id`` back onto the position, and
        auto-links any budget line whose ``boq_position_id`` matches. Re-running
        only fills gaps so it never doubles money or relinks already-wired rows.
        """
        from app.modules.boq.repository import BOQRepository, PositionRepository

        resolved_boq_id = boq_id
        if resolved_boq_id is None:
            resolved_boq_id = await self._cost_service.pick_default_boq(project_id)
            if resolved_boq_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No BOQ found for this project - create one first.",
                )

        # Confirm the BOQ belongs to this project (IDOR + correctness).
        boq = await BOQRepository(self.session).get_by_id(resolved_boq_id)
        if boq is None or boq.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="BOQ not found for this project",
            )

        position_repo = PositionRepository(self.session)
        positions, _ = await position_repo.list_for_boq(resolved_boq_id, limit=100000)
        if not positions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No positions found in the specified BOQ",
            )

        project_currency = await self._get_project_currency(project_id)

        # Resolve the classification standard once from the project config when
        # available; default to DIN 276 which is the most common in the seed set.
        standard = await self._resolve_classification_standard(project_id)

        # Cache existing accounts + lines so the whole generation is one pass.
        # Store only the account *id* (a plain UUID): the ORM object would be
        # expired by the first create/update inside the loop, and accessing
        # ``account.id`` afterwards would re-issue a sync SELECT and raise
        # MissingGreenlet under the async session.
        accounts_by_code: dict[str, uuid.UUID] = {
            a.code: a.id for a in await self.account_repo.list_for_project(project_id)
        }
        # ``lines_by_code`` only needs the identity + linkage columns, so we
        # snapshot them into plain namespaces up front. Reading the live ORM
        # objects later in the loop would fault: the first create/update flushes
        # and ``expire_all()``s the identity map, after which any ORM attribute
        # access (even on a previously-loaded row) re-issues a sync SELECT and
        # raises MissingGreenlet under the async session.
        lines_by_code: dict[str, SimpleNamespace] = {}
        for line in (await self.line_repo.list_for_project(project_id, limit=100000))[0]:
            lines_by_code[line.code] = SimpleNamespace(
                id=line.id,
                boq_position_id=line.boq_position_id,
                boq_id=line.boq_id,
                control_account_id=line.control_account_id,
            )

        accounts_created = 0
        cost_lines_created = 0
        positions_linked = 0

        # Snapshot every position attribute the loop needs BEFORE we mutate
        # anything. The first ``position_repo.update_fields`` / ``*_repo.create``
        # call inside the loop flushes and ``expire_all()``s the identity map;
        # without this snapshot the next iteration's ``pos.unit`` access would
        # trigger a sync lazy-load of an expired column and raise MissingGreenlet
        # under the async session. Reading the columns up front keeps generation
        # a single pass with no mid-loop expired-attribute IO.
        pos_views = [
            SimpleNamespace(
                id=pos.id,
                unit=pos.unit,
                classification=pos.classification,
                reference_code=getattr(pos, "reference_code", None),
                description=pos.description,
                quantity=pos.quantity,
                unit_rate=pos.unit_rate,
                total=pos.total,
                cost_line_id=getattr(pos, "cost_line_id", None),
            )
            for pos in positions
        ]

        for pos in pos_views:
            # Skip section headers (empty unit) - mirrors generate_budget_from_boq.
            if not pos.unit:
                continue

            # ── Control account from classification ──────────────────────
            account_id: uuid.UUID | None = None
            account_info = _account_code_from_classification(pos.classification, standard)
            if account_info is not None:
                acct_code, acct_name = account_info
                account_id = accounts_by_code.get(acct_code)
                if account_id is None:
                    account = ControlAccount(
                        project_id=project_id,
                        parent_id=None,
                        code=acct_code,
                        name=acct_name,
                        classification_standard=standard,
                        status="open",
                        sort_order=0,
                    )
                    account = await self.account_repo.create(account)
                    # Capture the id immediately; the ORM object expires on the
                    # next create/update inside this loop.
                    account_id = account.id
                    accounts_by_code[acct_code] = account_id
                    accounts_created += 1

            # ── Cost line code (reference_code or auto) ──────────────────
            ref = (pos.reference_code or "").strip()
            code = ref or f"CL-{uuid.uuid4().hex[:8].upper()}"
            # Guard against a collision on an auto code (extremely unlikely).
            while not ref and code in lines_by_code:
                code = f"CL-{uuid.uuid4().hex[:8].upper()}"

            existing_line = lines_by_code.get(code)
            if existing_line is None:
                new_line = CostLine(
                    project_id=project_id,
                    control_account_id=account_id,
                    code=code,
                    description=(pos.description or "")[:2000],
                    unit=pos.unit,
                    source="boq",
                    boq_position_id=pos.id,
                    boq_id=resolved_boq_id,
                    estimate_quantity=str(pos.quantity or "0"),
                    estimate_unit_rate=str(pos.unit_rate or "0"),
                    estimate_amount=str(pos.total or "0"),
                    currency=project_currency,
                    status="active",
                )
                new_line = await self.line_repo.create(new_line)
                # Capture identity NOW, before the next iteration expires it.
                view = SimpleNamespace(
                    id=new_line.id,
                    boq_position_id=pos.id,
                    boq_id=resolved_boq_id,
                    control_account_id=account_id,
                )
                lines_by_code[code] = view
                cost_lines_created += 1
            else:
                view = existing_line
                # Idempotent fill-nulls-only: attach the originating position /
                # account when the existing line has none yet, never overwrite.
                fill: dict[str, object] = {}
                if view.boq_position_id is None:
                    fill["boq_position_id"] = pos.id
                    view.boq_position_id = pos.id
                if view.boq_id is None:
                    fill["boq_id"] = resolved_boq_id
                    view.boq_id = resolved_boq_id
                if view.control_account_id is None and account_id is not None:
                    fill["control_account_id"] = account_id
                    view.control_account_id = account_id
                if fill:
                    await self.line_repo.update_fields(view.id, **fill)

            # ── Write cost_line_id back onto the position (fill-only) ────
            if pos.cost_line_id is None:
                await position_repo.update_fields(pos.id, cost_line_id=view.id)
                positions_linked += 1

        # ── Auto-link budget lines by boq_position_id (fill-nulls-only) ──
        # ``lines_by_code`` values are plain namespaces (id + linkage cols), so
        # the autolink pass never touches expired ORM state.
        budget_lines_linked = await self._autolink_budget_lines(project_id, lines_by_code)

        await _safe_publish(
            "costmodel.spine.generated",
            {
                "project_id": str(project_id),
                "boq_id": str(resolved_boq_id),
                "accounts_created": accounts_created,
                "cost_lines_created": cost_lines_created,
                "positions_linked": positions_linked,
                "budget_lines_linked": budget_lines_linked,
            },
            source_module="oe_costmodel",
        )
        logger.info(
            "Cost spine generated: project=%s boq=%s accounts=+%d lines=+%d positions_linked=%d budget_linked=%d",
            project_id,
            resolved_boq_id,
            accounts_created,
            cost_lines_created,
            positions_linked,
            budget_lines_linked,
        )
        return SpineGenerationResult(
            project_id=project_id,
            boq_id=resolved_boq_id,
            accounts_created=accounts_created,
            cost_lines_created=cost_lines_created,
            positions_linked=positions_linked,
            budget_lines_linked=budget_lines_linked,
        )

    async def _resolve_classification_standard(self, project_id: uuid.UUID) -> str:
        """Best-effort project classification standard, defaulting to ``din276``."""
        try:
            from app.modules.projects.repository import ProjectRepository

            project = await ProjectRepository(self.session).get_by_id(project_id)
        except Exception:
            return "din276"
        if project is None:
            return "din276"
        cfg = getattr(project, "config", None) or getattr(project, "settings", None)
        if isinstance(cfg, dict):
            std = str(cfg.get("classification_standard") or "").strip()
            if std:
                return std
        return "din276"

    async def _autolink_budget_lines(
        self,
        project_id: uuid.UUID,
        lines_by_code: dict[str, SimpleNamespace],
    ) -> int:
        """Link existing budget lines to cost lines by shared ``boq_position_id``.

        Fill-nulls-only: a budget line already carrying a ``cost_line_id`` is
        left untouched. Sets both ``cost_line_id`` and ``control_account_id`` so
        account rollups can group budget without re-joining.

        ``lines_by_code`` values are plain namespaces (id + linkage cols)
        captured by the generation loop, so this pass never reads an expired
        ORM attribute. Budget-line fields are likewise snapshotted before the
        first ``update_fields`` (which ``expire_all()``s) so a multi-row link
        does not fault on the second iteration.
        """
        # Index cost lines by their originating position.
        by_position: dict[str, SimpleNamespace] = {}
        for line in lines_by_code.values():
            if line.boq_position_id is not None:
                by_position[str(line.boq_position_id)] = line

        if not by_position:
            return 0

        budget_lines, _ = await self.budget_repo.list_for_project(project_id, limit=100000)
        # Snapshot the columns we branch on up front (see docstring).
        bl_views = [
            SimpleNamespace(
                id=bl.id,
                cost_line_id=bl.cost_line_id,
                boq_position_id=bl.boq_position_id,
            )
            for bl in budget_lines
        ]
        linked = 0
        for bl in bl_views:
            if bl.cost_line_id is not None or bl.boq_position_id is None:
                continue
            target = by_position.get(str(bl.boq_position_id))
            if target is None:
                continue
            await self.budget_repo.update_fields(
                bl.id,
                cost_line_id=target.id,
                control_account_id=target.control_account_id,
            )
            linked += 1
        return linked

    # ── Rollup ──────────────────────────────────────────────────────────────

    async def _build_links(self, project_id: uuid.UUID) -> dict[str, CostLineLinks]:
        """Collect every downstream reference per cost line in one sweep each.

        Returns a dict keyed by cost-line id string. Five scans (budget, BOQ
        positions, PO items, contract lines, RFQs) - no per-line queries.
        """
        from sqlalchemy import select

        from app.modules.boq.models import Position
        from app.modules.contracts.models import Contract, ContractLine
        from app.modules.procurement.models import PurchaseOrder, PurchaseOrderItem
        from app.modules.rfq_bidding.models import RFQ

        links: dict[str, CostLineLinks] = {}

        def _bucket(key: str) -> CostLineLinks:
            return links.setdefault(key, CostLineLinks())

        # Budget lines.
        stmt = select(BudgetLine.cost_line_id, BudgetLine.id).where(
            BudgetLine.project_id == project_id,
            BudgetLine.cost_line_id.is_not(None),
        )
        for cost_line_id, bl_id in (await self.session.execute(stmt)).all():
            _bucket(str(cost_line_id)).budget_line_ids.append(str(bl_id))

        # BOQ positions.
        stmt = select(Position.cost_line_id, Position.id).where(Position.cost_line_id.is_not(None))
        for cost_line_id, pos_id in (await self.session.execute(stmt)).all():
            _bucket(str(cost_line_id)).boq_position_ids.append(str(pos_id))

        # PO items (scoped to project via the parent PO).
        stmt = (
            select(PurchaseOrderItem.cost_line_id, PurchaseOrderItem.id)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.po_id)
            .where(
                PurchaseOrder.project_id == project_id,
                PurchaseOrderItem.cost_line_id.is_not(None),
            )
        )
        for cost_line_id, item_id in (await self.session.execute(stmt)).all():
            _bucket(str(cost_line_id)).po_item_ids.append(str(item_id))

        # Contract lines (scoped to project via the parent contract).
        stmt = (
            select(ContractLine.cost_line_id, ContractLine.id)
            .join(Contract, Contract.id == ContractLine.contract_id)
            .where(
                Contract.project_id == project_id,
                ContractLine.cost_line_id.is_not(None),
            )
        )
        for cost_line_id, cl_id in (await self.session.execute(stmt)).all():
            _bucket(str(cost_line_id)).contract_line_ids.append(str(cl_id))

        # RFQs carry a JSON array of cost-line ids.
        stmt = select(RFQ.id, RFQ.cost_line_ids).where(RFQ.project_id == project_id)
        for rfq_id, cost_line_ids in (await self.session.execute(stmt)).all():
            if isinstance(cost_line_ids, list):
                for raw in cost_line_ids:
                    if raw:
                        _bucket(str(raw)).rfq_ids.append(str(rfq_id))

        return links

    def _assemble_line_rollup(
        self,
        line: CostLine,
        *,
        budget: dict[str, dict[str, Decimal]],
        po: dict[str, Decimal],
        contracted: dict[str, Decimal],
        claimed: dict[str, Decimal],
        links: dict[str, CostLineLinks],
    ) -> CostLineRollupResponse:
        """Assemble one cost line's rollup from the pre-computed aggregate maps."""
        key = str(line.id)
        b = budget.get(key, {})
        budget_planned = b.get("planned", Decimal("0"))
        estimate_amount = Decimal(str(line.estimate_amount or "0"))
        return CostLineRollupResponse(
            cost_line_id=line.id,
            code=line.code,
            control_account_id=line.control_account_id,
            description=line.description,
            currency=line.currency,
            estimate_amount=estimate_amount,
            budget_planned=budget_planned,
            budget_committed=b.get("committed", Decimal("0")),
            budget_actual=b.get("actual", Decimal("0")),
            po_committed=po.get(key, Decimal("0")),
            contracted_value=contracted.get(key, Decimal("0")),
            claimed_to_date=claimed.get(key, Decimal("0")),
            variance_estimate_vs_budget=estimate_amount - budget_planned,
            links=links.get(key, CostLineLinks()),
        )

    async def _distinct_link_currencies(self, project_id: uuid.UUID) -> set[str]:
        """Distinct non-blank currencies across the linked cost-domain rows.

        Mirrors the existing ``_distinct_budget_currencies`` flag pattern but
        spans every spine source (budget lines, PO currency, contract currency,
        cost-line currency) so ``mixed_currency`` is True whenever a sum may
        have crossed a missing fx rate.
        """
        from sqlalchemy import select

        from app.modules.contracts.models import Contract, ContractLine
        from app.modules.procurement.models import PurchaseOrder, PurchaseOrderItem

        codes: set[str] = set()

        stmt = select(CostLine.currency).where(CostLine.project_id == project_id).distinct()
        for (raw,) in (await self.session.execute(stmt)).all():
            if (raw or "").strip():
                codes.add(raw.strip().upper())

        stmt = (
            select(BudgetLine.currency)
            .where(BudgetLine.project_id == project_id, BudgetLine.cost_line_id.is_not(None))
            .distinct()
        )
        for (raw,) in (await self.session.execute(stmt)).all():
            if (raw or "").strip():
                codes.add(raw.strip().upper())

        stmt = (
            select(PurchaseOrder.currency_code)
            .join(PurchaseOrderItem, PurchaseOrderItem.po_id == PurchaseOrder.id)
            .where(PurchaseOrder.project_id == project_id, PurchaseOrderItem.cost_line_id.is_not(None))
            .distinct()
        )
        for (raw,) in (await self.session.execute(stmt)).all():
            if (raw or "").strip():
                codes.add(raw.strip().upper())

        stmt = (
            select(Contract.currency)
            .join(ContractLine, ContractLine.contract_id == Contract.id)
            .where(Contract.project_id == project_id, ContractLine.cost_line_id.is_not(None))
            .distinct()
        )
        for (raw,) in (await self.session.execute(stmt)).all():
            if (raw or "").strip():
                codes.add(raw.strip().upper())

        return codes

    async def rollup_for_project(self, project_id: uuid.UUID) -> SpineRollupResponse:
        """Assemble the project-wide Cost Spine rollup from grouped aggregates."""
        accounts = await self.account_repo.list_for_project(project_id)
        lines, _ = await self.line_repo.list_for_project(project_id, limit=100000)

        budget = await self.spine_repo.budget_aggregate_by_cost_line(project_id)
        po = await self.spine_repo.po_committed_by_cost_line(project_id)
        contracted = await self.spine_repo.contract_value_by_cost_line(project_id)
        claimed = await self.spine_repo.claimed_to_date_by_cost_line(project_id)
        links = await self._build_links(project_id)

        line_rollups = [
            self._assemble_line_rollup(
                line,
                budget=budget,
                po=po,
                contracted=contracted,
                claimed=claimed,
                links=links,
            )
            for line in lines
        ]

        totals = {
            "estimate_amount": Decimal("0"),
            "budget_planned": Decimal("0"),
            "budget_committed": Decimal("0"),
            "budget_actual": Decimal("0"),
            "po_committed": Decimal("0"),
            "contracted_value": Decimal("0"),
            "claimed_to_date": Decimal("0"),
        }
        for r in line_rollups:
            totals["estimate_amount"] += r.estimate_amount
            totals["budget_planned"] += r.budget_planned
            totals["budget_committed"] += r.budget_committed
            totals["budget_actual"] += r.budget_actual
            totals["po_committed"] += r.po_committed
            totals["contracted_value"] += r.contracted_value
            totals["claimed_to_date"] += r.claimed_to_date
        totals_str = {k: str(v) for k, v in totals.items()}
        totals_str["variance_estimate_vs_budget"] = str(totals["estimate_amount"] - totals["budget_planned"])

        currency = await self._get_project_currency(project_id)
        mixed = len(await self._distinct_link_currencies(project_id)) > 1

        return SpineRollupResponse(
            currency=currency,
            mixed_currency=mixed,
            accounts=[_control_account_to_response(a) for a in accounts],
            lines=line_rollups,
            totals=totals_str,
        )

    async def rollup_for_line(self, line_id: uuid.UUID) -> CostLineRollupResponse:
        """Assemble the rollup for a single cost line. Raises 404 if missing."""
        line = await self.line_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost line not found")

        project_id = line.project_id
        budget = await self.spine_repo.budget_aggregate_by_cost_line(project_id)
        po = await self.spine_repo.po_committed_by_cost_line(project_id)
        contracted = await self.spine_repo.contract_value_by_cost_line(project_id)
        claimed = await self.spine_repo.claimed_to_date_by_cost_line(project_id)
        links = await self._build_links(project_id)

        return self._assemble_line_rollup(
            line,
            budget=budget,
            po=po,
            contracted=contracted,
            claimed=claimed,
            links=links,
        )

    # ── Link / unlink a downstream target ─────────────────────────────────────

    async def link_target(
        self,
        line_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
    ) -> CostLineRollupResponse:
        """Link a downstream entity to a cost line, then return its rollup.

        ``target_type`` is one of ``boq_position`` / ``budget_line`` /
        ``po_item`` / ``contract_line`` / ``rfq``. The target must belong to the
        same project as the cost line (404 on a cross-project / missing target).
        """
        line = await self.line_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost line not found")
        await self._apply_link(line, target_type, target_id, link=True)
        return await self.rollup_for_line(line_id)

    async def unlink_target(
        self,
        line_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
    ) -> CostLineRollupResponse:
        """Detach a downstream entity from a cost line, then return its rollup."""
        line = await self.line_repo.get_by_id(line_id)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cost line not found")
        await self._apply_link(line, target_type, target_id, link=False)
        return await self.rollup_for_line(line_id)

    async def _apply_link(
        self,
        line: CostLine,
        target_type: str,
        target_id: uuid.UUID,
        *,
        link: bool,
    ) -> None:
        """Set or clear ``cost_line_id`` on the target row after a project check."""
        from sqlalchemy import update

        from app.modules.boq.models import BOQ, Position
        from app.modules.contracts.models import Contract, ContractLine
        from app.modules.procurement.models import PurchaseOrder, PurchaseOrderItem
        from app.modules.rfq_bidding.models import RFQ

        project_id = line.project_id
        new_value = line.id if link else None
        normalized = (target_type or "").strip().lower()

        if normalized == "boq_position":
            pos = await self.session.get(Position, target_id)
            if pos is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            boq = await self.session.get(BOQ, pos.boq_id)
            if boq is None or boq.project_id != project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            await self.session.execute(update(Position).where(Position.id == target_id).values(cost_line_id=new_value))

        elif normalized == "budget_line":
            bl = await self.session.get(BudgetLine, target_id)
            if bl is None or bl.project_id != project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            await self.budget_repo.update_fields(
                target_id,
                cost_line_id=new_value,
                control_account_id=(line.control_account_id if link else None),
            )

        elif normalized == "po_item":
            item = await self.session.get(PurchaseOrderItem, target_id)
            if item is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            po = await self.session.get(PurchaseOrder, item.po_id)
            if po is None or po.project_id != project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            await self.session.execute(
                update(PurchaseOrderItem).where(PurchaseOrderItem.id == target_id).values(cost_line_id=new_value)
            )

        elif normalized == "contract_line":
            cl = await self.session.get(ContractLine, target_id)
            if cl is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            contract = await self.session.get(Contract, cl.contract_id)
            if contract is None or contract.project_id != project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            await self.session.execute(
                update(ContractLine).where(ContractLine.id == target_id).values(cost_line_id=new_value)
            )

        elif normalized == "rfq":
            rfq = await self.session.get(RFQ, target_id)
            if rfq is None or rfq.project_id != project_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
            current = list(rfq.cost_line_ids or [])
            line_id_str = str(line.id)
            if link:
                if line_id_str not in {str(c) for c in current}:
                    current.append(line_id_str)
            else:
                current = [c for c in current if str(c) != line_id_str]
            await self.session.execute(update(RFQ).where(RFQ.id == target_id).values(cost_line_ids=current))
            await self.session.flush()
            self.session.expire_all()

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Invalid target_type. Expected one of: boq_position, budget_line, "
                    "po_item, contract_line, rfq."
                ),
            )

        await self.session.flush()
        self.session.expire_all()
