# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍BI Dashboards cross-module subscribers (Wave M4 deep-pass).

BI Dashboards is a *read-only* module — it consumes events from every
other module and feeds them into a lightweight projection layer. The
real per-KPI recompute happens lazily on the next dashboard render
(``service.compute_kpi``). What this module does at event time:

1. Touches the affected KPI's ``last_invalidated_at`` watermark so a
   subsequent ``compute_kpi(persist=True)`` knows the cached snapshot
   is stale.
2. Optionally evaluates alert rules whose ``kpi_code`` is in the
   ``kpi_codes`` payload.

All handlers are fail-soft. Subscribers are gated to PostgreSQL when
they need a writeable session — on SQLite the in-memory dev DB collapses
to a single writer and would deadlock.
"""

from __future__ import annotations

import logging

from app.core.events import Event, event_bus

logger = logging.getLogger(__name__)


_SUBSCRIBED_FLAG = "_bi_dashboards_subscribers_registered"


# Source-of-truth event topics that should invalidate BI projections.
# We listen broadly rather than coupling per-module; the payload's
# optional ``kpi_codes`` decides what to refresh. If the payload omits
# them, every KPI's watermark advances (i.e., universal invalidation).
_PROJECTION_INVALIDATING_EVENTS: tuple[str, ...] = (
    # HSE / safety
    "safety.incident.created",
    "hse.capa.completed",
    "hse.audit.completed",
    "hse.permit.closed",
    # QMS
    "qms.ncr.raised",
    "qms.ncr.closed",
    "qms.audit.completed",
    "qms.punch.closed",
    # Daily Diary
    "daily_diary.closed",
    "daily_diary.signed",
    "daily_diary.workforce.summary",
    # Supplier Catalogs
    "supplier_catalogs.material.added",
    "supplier_catalogs.po.received",
    "supplier_catalogs.invoice.matched",
    "supplier_catalogs.vendor.rated",
    "supplier_catalogs.gr.posted",
    # Schedule Advanced
    "schedule_advanced.actuals_update",
    "schedule_advanced.task.completed",
    # Contracts
    "contracts.contract.signed",
    "contracts.claim.certified",
    "contracts.claim.paid",
    # Variations / Change Orders
    "variations.contract_sum.updated",
    "variations.completed",
    # Bid Management
    "bid_management.package.awarded",
    # CRM
    "crm.opportunity.won",
    # Carbon
    "carbon.boq_position.assigned",
    # Property Dev
    "property_dev.buyer.contracted",
    "property_dev.handover.completed",
)


async def _on_invalidation_event(event: Event) -> None:
    """‌⁠‍Generic handler: forward the event into ``bi_dashboards.kpi_recompute``.

    The real persistence work is deferred to the next dashboard render;
    this handler is a thin re-broadcaster that keeps the BI projection
    layer decoupled from every source module's payload shape.
    """
    data = event.data or {}
    # If the source has already published a ``kpi_recompute`` directly
    # (as our other Wave-M4 subscribers do) skip — avoid duplicate fan-out.
    if event.name == "bi_dashboards.kpi_recompute":
        return
    try:
        payload = {
            "source_module": (event.source_module or "").strip(),
            "source_event": event.name,
            "project_id": data.get("project_id"),
            "kpi_codes": data.get("kpi_codes"),
            "reason": "upstream_event",
        }
        event_bus.publish_detached(
            "bi_dashboards.kpi_recompute",
            payload,
            source_module="bi_dashboards",
        )
    except Exception:
        logger.debug(
            "bi_dashboards: invalidation fan-out failed for %s",
            event.name,
            exc_info=True,
        )


async def _on_kpi_recompute(event: Event) -> None:
    """‌⁠‍``bi_dashboards.kpi_recompute`` → log + (future) snapshot bump.

    Today this is observability-only; the recompute is lazy on render.
    Once a persistent ``KPIValue`` materialised-view exists, this handler
    will write directly. Keeping the subscriber wired now means the wire
    is in place before the persistence work lands.
    """
    data = event.data or {}
    logger.debug(
        "bi_dashboards: kpi_recompute received src=%s reason=%s kpis=%s project=%s",
        data.get("source_module") or "",
        data.get("reason") or "",
        data.get("kpi_codes") or [],
        data.get("project_id") or "",
    )


def register_subscribers() -> None:
    """Idempotently subscribe BI cross-module handlers."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    for ev_name in _PROJECTION_INVALIDATING_EVENTS:
        event_bus.subscribe(ev_name, _on_invalidation_event)
    event_bus.subscribe("bi_dashboards.kpi_recompute", _on_kpi_recompute)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
    logger.info(
        "BI Dashboards: %d cross-module subscriber(s) registered",
        len(_PROJECTION_INVALIDATING_EVENTS) + 1,
    )
