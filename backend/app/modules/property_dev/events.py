"""‌⁠‍Property Development event registry.

Documents events PUBLISHED by the property_dev module + wires
cross-module SUBSCRIBERS that mutate property_dev state in response to
events fired by other modules (``schedule``, ``correspondence``,
``documents``).

Events published (payload schemas in handler docstrings):

  Lead lifecycle:
    - ``property_dev.lead.created``         {lead_id, development_id?, source, status, email}
    - ``property_dev.lead.converted``       {lead_id, reservation_id, buyer_id?, plot_id, deposit_amount, currency}

  Reservation lifecycle:
    - ``property_dev.reservation.created``  {reservation_id, plot_id, lead_id?, buyer_id?, deposit_amount, currency}
    - ``property_dev.reservation.cancelled``{reservation_id, plot_id}
    - ``property_dev.reservation.expired``  {reservation_id, plot_id}

  SalesContract (SPA) lifecycle:
    - ``property_dev.spa.draft_created``     {spa_id, plot_id, total_value, currency}
    - ``property_dev.spa.created``           {spa_id, plot_id, reservation_id, total_value, currency}
    - ``property_dev.spa.sent_for_signature``{spa_id, envelope_id?, party_count}
    - ``property_dev.spa.signed``            {spa_id, plot_id, status, signing_date}
    - ``property_dev.spa.cancelled``         {spa_id}

  Payment lifecycle:
    - ``property_dev.payment_schedule.activated`` {schedule_id, sales_contract_id}
    - ``property_dev.payment_schedule.completed`` {schedule_id}
    - ``property_dev.instalment.paid``        {instalment_id, schedule_id, amount_paid, amount_total_paid, status}
    - ``property_dev.instalment.waived``      {instalment_id, schedule_id, reason}

  ContractParty:
    - ``property_dev.contract_party.added``   {spa_id, buyer_id, party_id, ownership_pct, party_role, ownership_total}
    - ``property_dev.contract_party.removed`` {spa_id, buyer_id, party_id}

  Cross-module signals fanned out by property_dev:
    - ``finance.cashflow.actual_received`` (mirrors ``instalment.paid``)
    - ``correspondence.outbound.requested`` (template=INSTALMENT_DEMAND)
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)


# ── Subscribers ─────────────────────────────────────────────────────────


async def _on_schedule_milestone_reached(event: Event) -> dict[str, Any]:
    """React to a ``schedule.milestone.reached`` event.

    Payload (best-effort):
        sales_contract_id?: UUID — when present, scope to that SPA.
        milestone_event: str — e.g. ``foundation_complete``.
        plot_id?: UUID — fallback when sales_contract_id is missing.

    Marks pending instalments whose ``milestone_event`` matches as due
    and auto-issues a demand letter for each affected line.
    """
    from app.modules.property_dev.service import PropertyDevService

    payload = event.data or {}
    milestone_event = payload.get("milestone_event") or payload.get("milestone")
    if not milestone_event:
        return {"status": "ignored", "reason": "no milestone_event in payload"}
    spa_id = payload.get("sales_contract_id") or payload.get("spa_id")

    try:
        async with async_session_factory() as session:
            svc = PropertyDevService(session)
            touched = 0
            if spa_id:
                import uuid as _uuid
                try:
                    spa_uuid = _uuid.UUID(str(spa_id))
                except (TypeError, ValueError):
                    return {"status": "ignored", "reason": "bad spa_id"}
                touched = await svc._fire_milestone(spa_uuid, milestone_event)
            else:
                # Fan out across every SPA — match by milestone alone.
                # Only used in tests/diagnostics; production callers
                # always supply spa_id.
                instalments = await svc.instalments.list_due_for_milestone(
                    milestone_event
                )
                for ins in instalments:
                    await svc.instalments.update_fields(ins.id, status="due")
                    touched += 1
            await session.commit()
            return {"status": "ok", "touched": touched}
    except Exception as exc:  # noqa: BLE001 — never crash event loop
        logger.warning(
            "property_dev._on_schedule_milestone_reached failed: %s", exc
        )
        return {"status": "error", "error": str(exc)}


async def _on_correspondence_outbound_delivered(
    event: Event,
) -> dict[str, Any]:
    """React to ``correspondence.outbound.delivered`` for demand letters.

    Payload:
        template: str — only INSTALMENT_DEMAND is handled here.
        instalment_id: UUID
        delivered_at?: str
        delivery_ref?: str

    Stamps ``metadata.demand_delivered_at`` + ``metadata.demand_ref`` on
    the matching instalment so the audit trail is preserved.
    """
    payload = event.data or {}
    if payload.get("template") != "INSTALMENT_DEMAND":
        return {"status": "ignored"}
    instalment_id = payload.get("instalment_id")
    if not instalment_id:
        return {"status": "ignored"}

    from app.modules.property_dev.repository import InstalmentRepository

    try:
        import uuid as _uuid
        try:
            ins_uuid = _uuid.UUID(str(instalment_id))
        except (TypeError, ValueError):
            return {"status": "ignored", "reason": "bad instalment_id"}

        async with async_session_factory() as session:
            repo = InstalmentRepository(session)
            ins = await repo.get_by_id(ins_uuid)
            if ins is None:
                return {"status": "ignored", "reason": "instalment gone"}
            md = dict(ins.metadata_ or {})
            md["demand_delivered_at"] = payload.get("delivered_at") or ""
            md["demand_ref"] = payload.get("delivery_ref") or ""
            await repo.update_fields(ins_uuid, metadata_=md)
            await session.commit()
            return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "property_dev._on_correspondence_outbound_delivered: %s", exc
        )
        return {"status": "error", "error": str(exc)}


async def _on_documents_uploaded(event: Event) -> dict[str, Any]:
    """React to ``documents.uploaded`` for category=spa.

    Payload:
        category: str — only ``spa`` is handled.
        external_id: str — envelope id / doc ref.
        sales_contract_id: UUID — required.

    Sets ``SalesContract.e_sign_envelope_id`` for cross-linking.
    """
    payload = event.data or {}
    if (payload.get("category") or "").lower() != "spa":
        return {"status": "ignored"}
    spa_id = payload.get("sales_contract_id") or payload.get("spa_id")
    envelope_id = payload.get("external_id") or payload.get("envelope_id")
    if not spa_id or not envelope_id:
        return {"status": "ignored"}

    from app.modules.property_dev.repository import SalesContractRepository

    try:
        import uuid as _uuid
        try:
            spa_uuid = _uuid.UUID(str(spa_id))
        except (TypeError, ValueError):
            return {"status": "ignored", "reason": "bad spa_id"}

        async with async_session_factory() as session:
            repo = SalesContractRepository(session)
            spa = await repo.get_by_id(spa_uuid)
            if spa is None:
                return {"status": "ignored", "reason": "spa gone"}
            await repo.update_fields(spa_uuid, e_sign_envelope_id=envelope_id)
            await session.commit()
            return {"status": "ok", "envelope_id": envelope_id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("property_dev._on_documents_uploaded failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def register_property_dev_event_subscribers() -> None:
    """Wire :class:`Event` subscribers for cross-module sources.

    Idempotent — safe to call multiple times because each subscription
    appends to the underlying handler list (the framework keeps it
    de-duplicated at startup via module loader call-once semantics).
    """
    event_bus.subscribe(
        "schedule.milestone.reached", _on_schedule_milestone_reached
    )
    event_bus.subscribe(
        "correspondence.outbound.delivered",
        _on_correspondence_outbound_delivered,
    )
    event_bus.subscribe("documents.uploaded", _on_documents_uploaded)
