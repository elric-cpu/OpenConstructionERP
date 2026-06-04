# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Payroll service - draft batch generation from field labour.

Deterministic, human-confirmed: generation aggregates already-recorded
labour hours (it never invents data) into a *draft* batch a manager then
reviews. Hours x cost_rate is evaluated in each source row's native
currency, then converted to the project base via the shared cost-model FX
helper so a batch never blends currencies.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.costmodel.repository import BudgetLineRepository, _amount_in_base
from app.modules.fieldreports.models import FieldReport, SiteWorkforceLog
from app.modules.payroll.events import EVENT_PAYROLL_BATCH_FINALIZED, safe_publish
from app.modules.payroll.models import PayrollBatch, PayrollEntry
from app.modules.payroll.repository import (
    PayrollBatchRepository,
    PayrollEntryRepository,
)

logger = logging.getLogger(__name__)

# Posting source family for labour-batch actuals. The cost spine is idempotent
# on (source_kind, source_ref); finalize uses the batch id as the stable ref so
# re-finalizing the same batch never double-posts its labour cost.
_PAYROLL_SOURCE_KIND = "payroll_batch"
# Cost category every labour-batch actual lands under in the cost spine.
_PAYROLL_COST_CATEGORY = "labor"
# Terminal status a finalized batch carries (the only state we post in).
_STATUS_DRAFT = "draft"
_STATUS_APPROVED = "approved"


def _finalize_idempotency_key(batch_id: uuid.UUID) -> str:
    """Deterministic SHA-256 idempotency key for finalizing *batch_id*.

    Stable across retries/replays (same batch -> same key) and collision-safe,
    so a double-finalize is recognised by the cost spine as the same posting.
    """
    return hashlib.sha256(str(batch_id).encode("utf-8")).hexdigest()


def _to_decimal(value: object) -> Decimal:
    """Coerce *value* to a non-negative finite Decimal, else 0."""
    if value is None:
        return Decimal("0")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    if not d.is_finite() or d < 0:
        return Decimal("0")
    return d


class _AggRow:
    """A mutable per-(worker, date) accumulator used during generation."""

    __slots__ = ("worker", "work_date", "resource_id", "rate", "currency", "hours", "source")

    def __init__(
        self,
        *,
        worker: str,
        work_date: str | None,
        resource_id: str | None,
        rate: Decimal,
        currency: str,
        source: str,
    ) -> None:
        self.worker = worker
        self.work_date = work_date
        self.resource_id = resource_id
        self.rate = rate
        self.currency = currency
        self.hours = Decimal("0")
        self.source = source


class PayrollService:
    """Business logic for payroll batches and entries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.batch_repo = PayrollBatchRepository(session)
        self.entry_repo = PayrollEntryRepository(session)
        self.budget_repo = BudgetLineRepository(session)

    # ── Rate resolution ─────────────────────────────────────────────────────

    async def _resource_rate(self, resource_id: str) -> tuple[Decimal, str]:
        """Return ``(default_cost_rate, currency)`` for a resource, or (0, "")."""
        try:
            rid = uuid.UUID(str(resource_id))
        except (ValueError, AttributeError, TypeError):
            return Decimal("0"), ""
        try:
            from app.modules.resources.repository import ResourceRepository

            resource = await ResourceRepository(self.session).get_by_id(rid)
        except Exception:
            return Decimal("0"), ""
        if resource is None:
            return Decimal("0"), ""
        rate = resource.default_cost_rate if resource.default_cost_rate is not None else Decimal("0")
        return _to_decimal(rate), (resource.currency or "").strip().upper()

    # ── Source collection ───────────────────────────────────────────────────

    async def _collect_workforce_logs(
        self,
        project_id: uuid.UUID,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        """Collect SiteWorkforceLog rows joined to their report date/project.

        Returns a list of normalised dicts: ``worker_type``, ``work_date``,
        ``hours`` (regular + overtime), ``resource_id`` / ``cost_rate`` /
        ``currency`` (from the log metadata when present).
        """
        stmt = (
            select(SiteWorkforceLog, FieldReport.report_date)
            .join(FieldReport, SiteWorkforceLog.field_report_id == FieldReport.id)
            .where(FieldReport.project_id == project_id)
        )
        if date_from:
            stmt = stmt.where(FieldReport.report_date >= date_from)
        if date_to:
            stmt = stmt.where(FieldReport.report_date <= date_to)

        result = await self.session.execute(stmt)
        rows: list[dict] = []
        for log, report_date in result.all():
            md = log.metadata_ if isinstance(log.metadata_, dict) else {}
            hours = _to_decimal(log.hours_worked) + _to_decimal(log.overtime_hours)
            if hours <= 0:
                continue
            row: dict = {
                "worker_type": log.worker_type or "labour",
                "work_date": str(report_date) if report_date is not None else None,
                "hours": hours,
                "headcount": int(log.headcount or 0),
                "source": "fieldreport",
            }
            if md.get("resource_id"):
                row["resource_id"] = str(md["resource_id"])
            if md.get("cost_rate") is not None:
                row["cost_rate"] = str(md["cost_rate"])
            if md.get("currency"):
                row["currency"] = str(md["currency"]).strip().upper()
            rows.append(row)
        return rows

    async def _collect_diary_hours(
        self,
        project_id: uuid.UUID,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        """Collect field-diary work hours for the project (best-effort).

        The diary module is an optional dependency; if its models are not
        loaded we simply skip this source rather than failing generation.
        """
        try:
            from app.modules.field_diary.models import DiaryActivity, DiaryEntry
        except Exception:
            return []

        stmt = (
            select(
                DiaryActivity.hours,
                DiaryActivity.activity_type,
                DiaryActivity.metadata_,
                DiaryEntry.entry_date,
            )
            .join(DiaryEntry, DiaryActivity.entry_id == DiaryEntry.id)
            .where(DiaryEntry.project_id == project_id)
        )
        if date_from:
            stmt = stmt.where(DiaryEntry.entry_date >= date_from)
        if date_to:
            stmt = stmt.where(DiaryEntry.entry_date <= date_to)

        try:
            result = await self.session.execute(stmt)
        except Exception:
            logger.debug("Field-diary hours unavailable for project=%s", project_id)
            return []

        rows: list[dict] = []
        for hours_raw, activity_type, md_raw, entry_date in result.all():
            if activity_type not in ("work", "inspection"):
                continue
            hours = _to_decimal(hours_raw)
            if hours <= 0:
                continue
            md = md_raw if isinstance(md_raw, dict) else {}
            row: dict = {
                "worker_type": str(activity_type),
                "work_date": str(entry_date) if entry_date is not None else None,
                "hours": hours,
                "headcount": 1,
                "source": "field_diary",
            }
            if md.get("resource_id"):
                row["resource_id"] = str(md["resource_id"])
            if md.get("cost_rate") is not None:
                row["cost_rate"] = str(md["cost_rate"])
            if md.get("currency"):
                row["currency"] = str(md["currency"]).strip().upper()
            rows.append(row)
        return rows

    # ── Aggregation core ────────────────────────────────────────────────────

    async def _aggregate(
        self,
        project_id: uuid.UUID,
        source_rows: list[dict],
    ) -> tuple[list[_AggRow], str, dict[str, str]]:
        """Aggregate source rows per (worker-key, date), resolving rates.

        Returns ``(agg_rows, base_currency, fx_map)``. The worker key is the
        ``resource_id`` when present (so multiple logs for the same person on
        the same day merge), else the ``worker_type`` label.
        """
        base, fx = await self.budget_repo._project_fx_context(project_id)
        buckets: dict[tuple[str, str | None], _AggRow] = {}

        for row in source_rows:
            hours = _to_decimal(row.get("hours"))
            if hours <= 0:
                continue

            resource_id = row.get("resource_id")
            rate = _to_decimal(row.get("cost_rate"))
            currency = str(row.get("currency") or "").strip().upper()
            if rate <= 0 and resource_id:
                rate, res_ccy = await self._resource_rate(str(resource_id))
                if not currency:
                    currency = res_ccy

            worker_key = str(resource_id) if resource_id else str(row.get("worker_type") or "labour")
            work_date = row.get("work_date")
            key = (worker_key, work_date)

            agg = buckets.get(key)
            if agg is None:
                agg = _AggRow(
                    worker=str(row.get("worker_type") or worker_key),
                    work_date=work_date,
                    resource_id=str(resource_id) if resource_id else None,
                    rate=rate,
                    currency=currency,
                    source=str(row.get("source") or "fieldreport"),
                )
                buckets[key] = agg
            else:
                # Keep the first non-zero rate/currency seen for the worker/day.
                if agg.rate <= 0 and rate > 0:
                    agg.rate = rate
                if not agg.currency and currency:
                    agg.currency = currency
            agg.hours += hours

        return list(buckets.values()), base, fx

    # ── Generation ──────────────────────────────────────────────────────────

    async def generate_batch(
        self,
        project_id: uuid.UUID,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        period_label: str | None = None,
        notes: str = "",
        user_id: str | None = None,
    ) -> tuple[PayrollBatch, list[PayrollEntry]]:
        """Generate a DRAFT payroll batch from field labour for a project.

        Raises 404 when there is no labour to aggregate so the caller gets a
        clear signal rather than an empty zero-total batch.
        """
        source_rows = await self._collect_workforce_logs(project_id, date_from=date_from, date_to=date_to)
        source_rows += await self._collect_diary_hours(project_id, date_from=date_from, date_to=date_to)

        agg_rows, base, fx = await self._aggregate(project_id, source_rows)
        if not agg_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No field labour found to generate a payroll batch",
            )

        created_by: uuid.UUID | None = None
        if user_id:
            try:
                created_by = uuid.UUID(str(user_id))
            except (ValueError, AttributeError, TypeError):
                created_by = None

        dates = sorted(a.work_date for a in agg_rows if a.work_date)
        span_start = dates[0] if dates else date_from
        span_end = dates[-1] if dates else date_to
        label = period_label or (f"{span_start} - {span_end}" if span_start and span_end else "Field labour")

        batch = PayrollBatch(
            project_id=project_id,
            period_label=label[:120],
            period_start=span_start,
            period_end=span_end,
            status="draft",
            currency=base,
            notes=notes,
            created_by=created_by,
        )
        batch = await self.batch_repo.create(batch)

        entries: list[PayrollEntry] = []
        total_hours = Decimal("0")
        total_amount = Decimal("0")
        for agg in agg_rows:
            # amount = hours x rate in native currency, converted to base.
            amount_native = agg.hours * agg.rate
            amount_base = _amount_in_base(str(amount_native), agg.currency, base, fx)
            total_hours += agg.hours
            total_amount += amount_base
            entries.append(
                PayrollEntry(
                    batch_id=batch.id,
                    resource_id=(uuid.UUID(agg.resource_id) if agg.resource_id else None),
                    worker=agg.worker[:255],
                    work_date=agg.work_date,
                    hours=str(agg.hours.quantize(Decimal("0.01"))),
                    rate=str(agg.rate.quantize(Decimal("0.0001"))),
                    amount=str(amount_base.quantize(Decimal("0.01"))),
                    currency=base,
                    source=agg.source,
                )
            )

        await self.entry_repo.bulk_create(entries)

        await self.batch_repo.update_fields(
            batch.id,
            total_hours=str(total_hours.quantize(Decimal("0.01"))),
            total_amount=str(total_amount.quantize(Decimal("0.01"))),
            entry_count=len(entries),
        )
        await self.session.refresh(batch)

        logger.info(
            "Payroll batch generated: project=%s entries=%d hours=%s amount=%s %s",
            project_id,
            len(entries),
            total_hours,
            total_amount,
            base,
        )
        return batch, entries

    # ── Read ─────────────────────────────────────────────────────────────────

    async def list_batches(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[PayrollBatch], int]:
        return await self.batch_repo.list_for_project(project_id, offset=offset, limit=limit)

    async def get_batch(self, batch_id: uuid.UUID) -> PayrollBatch:
        batch = await self.batch_repo.get_by_id(batch_id)
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payroll batch not found",
            )
        return batch

    async def list_entries(self, batch_id: uuid.UUID) -> list[PayrollEntry]:
        return await self.entry_repo.list_for_batch(batch_id)

    # ── Finalize (draft -> approved, post labour cost to the cost spine) ─────

    async def finalize_batch(self, batch_id: uuid.UUID) -> PayrollBatch:
        """Approve a draft batch and post its labour cost to the cost spine.

        Idempotent and safe to retry:
            * 404 when the batch does not exist.
            * Already ``approved`` -> returns the batch unchanged (no re-post).
            * Any other (non-draft) status -> 400 (cannot finalize).
            * Otherwise: sums the batch entries (already in project base
              currency), posts the labour actual onto the project's cost-spine
              labour budget line via the shared
              :meth:`CostSpineService.post_actual_to_budget_line` (idempotent on
              ``(source_kind="payroll_batch", source_ref=str(batch.id))``),
              flips ``status`` to ``approved`` and emits
              ``payroll.batch.finalized``.

        The posting amount is the batch's denormalised ``total_amount`` (the sum
        of its entry amounts), which the generator already converted to the
        project base currency - finalize only sums, it never re-applies FX, so a
        rate change after generation cannot retroactively move a finalized
        amount. A zero-entry / zero-total batch still transitions to approved but
        posts nothing (the spine is a pure accumulator; posting 0 is a harmless
        no-op, but we skip it to avoid a noisy 0.00 posting trail entry).

        Args:
            batch_id: The batch to finalize.

        Returns:
            The updated (or already-approved) :class:`PayrollBatch`.

        Raises:
            HTTPException: 404 if the batch is missing, 400 if it is in a status
                that cannot be finalized.
        """
        batch = await self.get_batch(batch_id)

        # Idempotent: a second finalize on an already-approved batch is a 200
        # no-op. The cost-spine posting is independently idempotent, but short
        # -circuiting here avoids re-touching the row and re-emitting the event.
        if batch.status == _STATUS_APPROVED:
            return batch

        if batch.status != _STATUS_DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot finalize a batch in status '{batch.status}' (must be 'draft').",
            )

        # Sum the entry amounts. These are persisted in the batch currency
        # (project base) by the generator, so this is a plain Decimal sum with
        # no FX. We prefer summing live entries over trusting the denormalised
        # total so a hand-edited entry is reflected, then fall back to the
        # stored total if (defensively) no entries are returned.
        entries = await self.entry_repo.list_for_batch(batch_id)
        total = Decimal("0")
        for entry in entries:
            total += _to_decimal(entry.amount)
        if not entries:
            total = _to_decimal(batch.total_amount)
        total = total.quantize(Decimal("0.01"))

        currency = (batch.currency or "").strip().upper()
        budget_line_id: uuid.UUID | None = None

        # Post the labour actual to the cost spine. Skip a strictly-zero amount:
        # the spine is a pure accumulator and a 0.00 posting only clutters the
        # audit trail without changing any total.
        if total > 0:
            if not currency:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Batch has no currency - cannot post labour cost to the budget.",
                )
            from app.modules.costmodel.service import CostSpineService

            spine_service = CostSpineService(self.session)
            line = await spine_service.post_actual_to_budget_line(
                project_id=batch.project_id,
                cost_line_id=None,
                cost_category=_PAYROLL_COST_CATEGORY,
                amount_base=str(total),
                currency=currency,
                source_kind=_PAYROLL_SOURCE_KIND,
                source_ref=str(batch.id),
                idempotency_key=_finalize_idempotency_key(batch.id),
            )
            budget_line_id = line.id

        # Flip status only after a successful post (post raises on failure, so a
        # failed posting leaves the batch in draft for a safe retry).
        await self.batch_repo.update_fields(batch.id, status=_STATUS_APPROVED)
        await self.session.refresh(batch)

        await safe_publish(
            EVENT_PAYROLL_BATCH_FINALIZED,
            {
                "project_id": str(batch.project_id),
                "batch_id": str(batch.id),
                "amount": str(total),
                "currency": currency,
                "budget_line_id": str(budget_line_id) if budget_line_id else None,
            },
        )

        logger.info(
            "Payroll batch finalized: project=%s batch=%s amount=%s %s budget_line=%s",
            batch.project_id,
            batch.id,
            total,
            currency,
            budget_line_id,
        )
        return batch

    # ── Labour cost rollup (for surfacing alongside the cost model) ──────────

    async def labour_cost(
        self,
        project_id: uuid.UUID,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[Decimal, Decimal, str]:
        """Return ``(labour_cost_base, total_hours, base_currency)`` live.

        A read-only mirror of the generation math - lets the UI show a
        "Labour cost" figure without persisting a batch.
        """
        source_rows = await self._collect_workforce_logs(project_id, date_from=date_from, date_to=date_to)
        source_rows += await self._collect_diary_hours(project_id, date_from=date_from, date_to=date_to)
        agg_rows, base, fx = await self._aggregate(project_id, source_rows)

        total_hours = Decimal("0")
        total_amount = Decimal("0")
        for agg in agg_rows:
            amount_native = agg.hours * agg.rate
            total_amount += _amount_in_base(str(amount_native), agg.currency, base, fx)
            total_hours += agg.hours
        return total_amount.quantize(Decimal("0.01")), total_hours.quantize(Decimal("0.01")), base
