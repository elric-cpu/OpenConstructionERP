"""‌⁠‍Property Development module permission definitions.

R6 (task #137) extends the original coarse set with fine-grained
permissions for the Lead / Reservation / SalesContract /
PaymentSchedule / Instalment / ContractParty pipeline. The original
permissions are kept verbatim so existing routes don't churn.
"""

from app.core.permissions import Role, permission_registry

PROPERTY_DEV_PERMISSIONS: dict[str, Role] = {
    # ── Foundation (v3018) ──────────────────────────────────────────
    "property_dev.read": Role.VIEWER,
    "property_dev.create": Role.EDITOR,
    "property_dev.update": Role.EDITOR,
    "property_dev.delete": Role.MANAGER,
    "property_dev.reserve_plot": Role.EDITOR,
    "property_dev.contract_buyer": Role.MANAGER,
    "property_dev.lock_selection": Role.MANAGER,
    "property_dev.handover": Role.MANAGER,
    "property_dev.fix_snag": Role.EDITOR,
    "property_dev.process_warranty": Role.EDITOR,
    # ── R6 — Lead ───────────────────────────────────────────────────
    "property_dev.lead.create": Role.EDITOR,
    "property_dev.lead.read": Role.VIEWER,
    "property_dev.lead.update": Role.EDITOR,
    "property_dev.lead.delete": Role.MANAGER,
    "property_dev.lead.assign": Role.MANAGER,
    "property_dev.lead.convert": Role.MANAGER,
    # ── R6 — Reservation ────────────────────────────────────────────
    "property_dev.reservation.create": Role.EDITOR,
    "property_dev.reservation.read": Role.VIEWER,
    "property_dev.reservation.update": Role.EDITOR,
    "property_dev.reservation.cancel": Role.MANAGER,
    "property_dev.reservation.expire": Role.MANAGER,
    # ── R6 — Sales Contract (SPA) ───────────────────────────────────
    "property_dev.spa.draft": Role.EDITOR,
    "property_dev.spa.send": Role.MANAGER,
    "property_dev.spa.sign": Role.MANAGER,
    "property_dev.spa.cancel": Role.MANAGER,
    # ── R6 — Payment Schedule ───────────────────────────────────────
    "property_dev.payment_schedule.activate": Role.MANAGER,
    "property_dev.payment_schedule.suspend": Role.MANAGER,
    # ── R6 — Instalment ─────────────────────────────────────────────
    "property_dev.instalment.mark_paid": Role.EDITOR,
    "property_dev.instalment.issue_demand": Role.EDITOR,
    "property_dev.instalment.waive": Role.MANAGER,
    # ── R6 — Contract Party (multi-buyer junction) ──────────────────
    "property_dev.contract_party.add": Role.EDITOR,
    "property_dev.contract_party.remove": Role.MANAGER,
    "property_dev.contract_party.update_ownership": Role.MANAGER,
}


def register_property_dev_permissions() -> None:
    """‌⁠‍Register permissions for the property_dev module."""
    permission_registry.register_module_permissions(
        "property_dev",
        PROPERTY_DEV_PERMISSIONS,
    )
