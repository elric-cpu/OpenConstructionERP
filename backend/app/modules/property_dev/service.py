"""‌⁠‍Property Development service — business logic + state machines.

Pure helpers (no DB / I/O) live at module top so tests can exercise them
directly. The :class:`PropertyDevService` orchestrates them against the
session + repositories.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.modules.property_dev.models import (
    Buyer,
    BuyerOption,
    BuyerOptionGroup,
    BuyerSelection,
    BuyerSelectionItem,
    ContractParty,
    Development,
    Handover,
    HandoverDoc,
    HouseType,
    HouseTypeVariant,
    Instalment,
    Lead,
    PaymentSchedule,
    Plot,
    Reservation,
    SalesContract,
    SalesContractRevision,
    Snag,
    WarrantyClaim,
)
from app.modules.property_dev.repository import (
    BuyerOptionGroupRepository,
    BuyerOptionRepository,
    BuyerPipelineQueries,
    BuyerRepository,
    BuyerSelectionItemRepository,
    BuyerSelectionRepository,
    ContractPartyRepository,
    DevelopmentRepository,
    HandoverDocRepository,
    HandoverRepository,
    HouseTypeRepository,
    HouseTypeVariantRepository,
    InstalmentRepository,
    LeadRepository,
    PaymentScheduleRepository,
    PlotRepository,
    ReservationRepository,
    SalesContractRepository,
    SalesContractRevisionRepository,
    SnagRepository,
    WarrantyClaimRepository,
)
from app.modules.property_dev.schemas import (
    BuyerCancelRequest,
    BuyerContractRequest,
    BuyerCreate,
    BuyerOptionCreate,
    BuyerOptionGroupCreate,
    BuyerOptionGroupUpdate,
    BuyerOptionUpdate,
    BuyerSelectionCreate,
    BuyerSelectionItemCreate,
    BuyerSelectionUpdate,
    BuyerUpdate,
    ContractPartyCreate,
    ContractPartyUpdate,
    DevelopmentCreate,
    DevelopmentUpdate,
    HandoverCompleteRequest,
    HandoverCreate,
    HandoverDocCreate,
    HandoverDocUpdate,
    HandoverUpdate,
    HouseTypeCreate,
    HouseTypeUpdate,
    HouseTypeVariantCreate,
    HouseTypeVariantUpdate,
    InstalmentCreate,
    InstalmentMarkPaidRequest,
    InstalmentUpdate,
    InstalmentWaiveRequest,
    LeadConvertToReservationRequest,
    LeadCreate,
    LeadUpdate,
    PaymentScheduleCreate,
    PaymentScheduleUpdate,
    PlotCreate,
    PlotReserveRequest,
    PlotUpdate,
    ReservationConvertToSpaRequest,
    ReservationCreate,
    ReservationUpdate,
    SalesContractCreate,
    SalesContractSendForSignatureRequest,
    SalesContractSignRequest,
    SalesContractUpdate,
    SnagCreate,
    SnagUpdate,
    WarrantyClaimCreate,
    WarrantyClaimUpdate,
)

logger = logging.getLogger(__name__)


# ── State machines ──────────────────────────────────────────────────────


_PLOT_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"reserved", "under_construction", "ready"},
    "reserved": {"planned", "under_construction", "ready", "sold"},
    "under_construction": {"ready", "reserved"},
    "ready": {"reserved", "sold", "under_construction"},
    "sold": {"handed_over"},
    "handed_over": set(),
}

_BUYER_TRANSITIONS: dict[str, set[str]] = {
    "lead": {"reserved", "cancelled"},
    "reserved": {"contracted", "cancelled", "lead"},
    "contracted": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

_SELECTION_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"locked", "draft", "cancelled"},
    "locked": {"cancelled"},
    "cancelled": set(),
}

_HANDOVER_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {"in_progress", "completed", "cancelled"},
    "in_progress": {"completed", "scheduled", "cancelled"},
    "completed": set(),
    "cancelled": {"scheduled"},
}

_WARRANTY_TRANSITIONS: dict[str, set[str]] = {
    "raised": {"under_review", "rejected", "closed"},
    "under_review": {"accepted", "rejected", "closed"},
    "accepted": {"closed"},
    "rejected": {"closed"},
    "closed": set(),
}


# ── R6 FSMs ─────────────────────────────────────────────────────────────


_LEAD_TRANSITIONS: dict[str, set[str]] = {
    "new": {"qualified", "lost", "disqualified"},
    "qualified": {
        "viewing_scheduled",
        "quotation_sent",
        "negotiating",
        "lost",
        "disqualified",
    },
    "viewing_scheduled": {"visited", "lost", "disqualified"},
    "visited": {
        "quotation_sent",
        "negotiating",
        "converted",
        "lost",
        "disqualified",
    },
    "quotation_sent": {"negotiating", "converted", "lost"},
    "negotiating": {"quotation_sent", "converted", "lost"},
    "converted": set(),
    "lost": set(),
    "disqualified": set(),
}


_RESERVATION_TRANSITIONS: dict[str, set[str]] = {
    "active": {"converted", "expired", "cancelled", "refunded"},
    "converted": set(),
    "expired": {"refunded"},
    "cancelled": {"refunded"},
    "refunded": set(),
}


_SPA_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"sent_for_signature", "cancelled"},
    "sent_for_signature": {"partially_signed", "signed", "cancelled"},
    "partially_signed": {"signed", "cancelled"},
    "signed": {"countersigned", "cancelled"},
    "countersigned": {"registered", "cancelled"},
    "registered": set(),
    "cancelled": set(),
}


_PAYMENT_SCHEDULE_TRANSITIONS: dict[str, set[str]] = {
    "active": {"suspended", "completed", "cancelled"},
    "suspended": {"active", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


_INSTALMENT_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"due", "waived", "cancelled"},
    "due": {"overdue", "paid", "waived", "cancelled"},
    "overdue": {"paid", "waived", "cancelled"},
    "paid": set(),
    "waived": set(),
    "cancelled": set(),
}


def allowed_lead_transitions(current: str) -> set[str]:
    """Return the set of next valid Lead statuses."""
    return set(_LEAD_TRANSITIONS.get(current, set()))


def allowed_reservation_transitions(current: str) -> set[str]:
    """Return the set of next valid Reservation statuses."""
    return set(_RESERVATION_TRANSITIONS.get(current, set()))


def allowed_spa_transitions(current: str) -> set[str]:
    """Return the set of next valid SalesContract statuses."""
    return set(_SPA_TRANSITIONS.get(current, set()))


def allowed_payment_schedule_transitions(current: str) -> set[str]:
    """Return the set of next valid PaymentSchedule statuses."""
    return set(_PAYMENT_SCHEDULE_TRANSITIONS.get(current, set()))


def allowed_instalment_transitions(current: str) -> set[str]:
    """Return the set of next valid Instalment statuses."""
    return set(_INSTALMENT_TRANSITIONS.get(current, set()))


def allowed_plot_transitions(current: str) -> set[str]:
    """‌⁠‍Return the set of next valid plot statuses."""
    return set(_PLOT_TRANSITIONS.get(current, set()))


def allowed_buyer_transitions(current: str) -> set[str]:
    """‌⁠‍Return the set of next valid buyer statuses."""
    return set(_BUYER_TRANSITIONS.get(current, set()))


def allowed_selection_transitions(current: str) -> set[str]:
    """Return the set of next valid buyer-selection statuses."""
    return set(_SELECTION_TRANSITIONS.get(current, set()))


def allowed_handover_transitions(current: str) -> set[str]:
    """Return the set of next valid handover progress states."""
    return set(_HANDOVER_TRANSITIONS.get(current, set()))


def allowed_warranty_transitions(current: str) -> set[str]:
    """Return the set of next valid warranty-claim statuses."""
    return set(_WARRANTY_TRANSITIONS.get(current, set()))


def _ensure_transition(
    name: str,
    current: str,
    target: str,
    allowed_fn,
) -> None:
    if target == current:
        return
    if target not in allowed_fn(current):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid {name} transition: {current} -> {target}",
        )


# ── Pure helpers ────────────────────────────────────────────────────────


def compute_freeze_deadline(handover_date: date, freeze_offset_days: int) -> date:
    """Return the date by which the buyer must lock their selection.

    Pure: no I/O. ``freeze_offset_days`` is subtracted from ``handover_date``.
    Negative offsets are clamped to 0.
    """
    if freeze_offset_days < 0:
        freeze_offset_days = 0
    return handover_date - timedelta(days=freeze_offset_days)


def compute_buyer_selection_total(items: Iterable[Any]) -> Decimal:
    """Sum ``quantity * unit_price_snapshot`` across items.

    Accepts ORM objects, dataclasses or dicts with the same attribute names.
    Pure: no DB.
    """
    total = Decimal("0")
    for item in items:
        qty = _attr(item, "quantity", 1)
        unit_price = _attr(item, "unit_price_snapshot", Decimal("0"))
        total += Decimal(str(qty)) * Decimal(str(unit_price))
    return total


def _attr(obj: Any, name: str, default: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def validate_option_compatibility(
    selected_option_ids: Iterable[Any],
    all_options: Iterable[Any],
    rules: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Validate the buyer's selection against compatibility_rules.

    The rules live on each ``BuyerOption.compatibility_rules`` JSON column
    in the form::

        {"must_have": ["opt_code", ...], "must_not_have": ["opt_code", ...]}

    Args:
        selected_option_ids: Iterable of option ids the buyer picked.
        all_options: Iterable of option-like objects (must expose ``id``,
            ``code``, ``compatibility_rules``).
        rules: Optional explicit rules dict (overrides per-option rules
            when provided — handy for tests).

    Returns:
        ``(ok, violations)``: ``ok`` is False when any rule fails;
        ``violations`` is a human-readable message list.
    """
    by_id: dict[Any, Any] = {_attr(o, "id", None): o for o in all_options}
    selected_set = {oid for oid in selected_option_ids if oid in by_id}
    selected_codes = {_attr(by_id[oid], "code", "") for oid in selected_set}

    violations: list[str] = []

    if rules is not None:
        violations.extend(_check_rules(rules, selected_codes))
    else:
        for oid in selected_set:
            opt = by_id[oid]
            opt_rules = _attr(opt, "compatibility_rules", {}) or {}
            code = _attr(opt, "code", "")
            for msg in _check_rules(opt_rules, selected_codes, requester_code=code):
                violations.append(msg)

    return (not violations, violations)


def _check_rules(
    rules: dict[str, Any],
    selected_codes: set[str],
    requester_code: str | None = None,
) -> list[str]:
    out: list[str] = []
    must_have = rules.get("must_have") or []
    must_not_have = rules.get("must_not_have") or []
    prefix = f"{requester_code}: " if requester_code else ""
    for code in must_have:
        if code not in selected_codes:
            out.append(f"{prefix}requires '{code}'")
    for code in must_not_have:
        if code in selected_codes:
            out.append(f"{prefix}incompatible with '{code}'")
    return out


def compute_plot_final_price(
    plot: Any,
    variant: Any | None,
    selections: Iterable[Any],
) -> Decimal:
    """Return the buyer's all-in price for the plot.

    Formula:
        base + (base * modifier_pct / 100) + sum(selection.total_price)

    Pure: no DB.
    """
    base = Decimal(str(_attr(plot, "price_base", 0)))
    modifier_value = Decimal("0")
    if variant is not None:
        pct = Decimal(str(_attr(variant, "modifier_pct", 0)))
        modifier_value = base * pct / Decimal("100")
    selections_total = Decimal("0")
    for sel_item in selections:
        selections_total += Decimal(str(_attr(sel_item, "total_price", 0)))
    return base + modifier_value + selections_total


def can_modify_selection(buyer: Any, today: date) -> bool:
    """Return True if the buyer can still edit their option selection.

    Rules:
        - Buyer status must not be ``locked``/``cancelled``/``completed``.
        - Today must be strictly before ``buyer.freeze_deadline`` (if set).
    """
    buyer_status = _attr(buyer, "status", "lead")
    if buyer_status in {"cancelled", "completed"}:
        return False
    deadline = _attr(buyer, "freeze_deadline", None)
    if deadline is None:
        return True
    if isinstance(deadline, str):
        try:
            deadline = date.fromisoformat(deadline[:10])
        except (TypeError, ValueError):
            return True
    return today < deadline


def derive_plot_construction_progress(
    plot_id: uuid.UUID, work_packages: Iterable[dict[str, Any]]
) -> Decimal:
    """Return overall construction % for a plot from a work-package list.

    Each work package is expected to be a dict with ``plot_id``, ``weight``
    (relative importance, default 1) and ``percent_complete`` (0-100).
    Pure: external schedulers feed in the packages.
    """
    weight_total = Decimal("0")
    weighted_progress = Decimal("0")
    for pkg in work_packages:
        if str(pkg.get("plot_id")) != str(plot_id):
            continue
        weight = Decimal(str(pkg.get("weight", 1)))
        pct = Decimal(str(pkg.get("percent_complete", 0)))
        weight_total += weight
        weighted_progress += weight * pct
    if weight_total == 0:
        return Decimal("0")
    return (weighted_progress / weight_total).quantize(Decimal("0.01"))


# ── Deposit forfeiture ──────────────────────────────────────────────────


# Each rule: (forfeit_fraction, citation, summary)
# fraction = Decimal between 0 and 1 representing the SHARE OF THE DEPOSIT
# kept by the developer. Fractions > 1 mean the developer must pay the
# buyer 2x deposit penalty (Spain LOE retraction at developer fault — but
# we model only buyer-initiated cancellations here; developer-side
# defaults are handled separately in the cancellation reason chain).
_DEPOSIT_FORFEITURE_RULES: dict[str, tuple[Decimal, str, str]] = {
    "GB": (
        Decimal("1.00"),
        "PRA CP21/22 + UK SRA Property Standards",
        "Buyer forfeits full deposit after exchange of contracts; "
        "before exchange — full refund (cooling-off period applies).",
    ),
    "IE": (
        Decimal("1.00"),
        "Law Society of Ireland — Standard Conditions of Sale 2023",
        "Buyer forfeits 10% deposit on rescission after binding contract.",
    ),
    "ES": (
        Decimal("1.00"),
        "Código Civil Art. 1454 — Arras Penitenciales",
        "Buyer loses full deposit on retraction; seller-default is "
        "2x deposit but is handled in seller-cancellation flow.",
    ),
    "PT": (
        Decimal("1.00"),
        "Código Civil Português Art. 442 — Sinal",
        "Buyer forfeits sinal (deposit) on contract rescission.",
    ),
    "AE": (
        Decimal("1.00"),
        "RERA Dubai Law No. (8) of 2007 — Article 11",
        "RERA escrow holds deposit; buyer forfeits full deposit on "
        "default after 30-day notice period if developer is not at fault.",
    ),
    "SA": (
        Decimal("1.00"),
        "Saudi Real Estate General Authority — Escrow Account Regs",
        "Buyer forfeits full deposit on default; seller delivers refund "
        "only when default is attributable to developer.",
    ),
    "US": (
        Decimal("1.00"),
        "Uniform Land Transactions Act (state-by-state)",
        "Earnest money typically forfeited on buyer default; "
        "state-specific overrides may reduce amount.",
    ),
    "DE": (
        Decimal("0.00"),
        "BGB §§ 311b, 313 — notarized purchase contract",
        "No standard deposit forfeiture under German civil code; "
        "developer may claim damages but no automatic deposit penalty.",
    ),
    "FR": (
        Decimal("1.00"),
        "Code civil Art. 1590 — arrhes",
        "Buyer forfeits arrhes on rescission; seller delivers 2x arrhes "
        "if seller withdraws.",
    ),
    "AU": (
        Decimal("1.00"),
        "Conveyancing Act (state-by-state) — typically 10% deposit",
        "Buyer forfeits deposit on default after cooling-off (typically "
        "5 business days).",
    ),
}

_DEFAULT_FORFEITURE_RULE: tuple[Decimal, str, str] = (
    Decimal("1.00"),
    "Generic common-law forfeiture",
    "No jurisdiction-specific rule loaded; full deposit forfeited "
    "on buyer-initiated cancellation (generic default).",
)


def compute_deposit_forfeiture(
    deposit_amount: Decimal | float | int | str,
    jurisdiction: str | None,
    cancelled_before_contract: bool = False,
) -> dict[str, Any]:
    """Return forfeiture amount + jurisdiction-cited rule.

    When ``cancelled_before_contract`` is True, the buyer is still in
    cooling-off / pre-exchange window — full refund regardless of
    jurisdiction.

    Pure: no DB. Always uses a real, citable rule (no random defaults).
    """
    amount = Decimal(str(deposit_amount or 0))
    code = (jurisdiction or "").strip().upper()

    if cancelled_before_contract:
        return {
            "jurisdiction": code or "—",
            "deposit_amount": amount,
            "forfeited_amount": Decimal("0"),
            "refundable_amount": amount,
            "rule_citation": "Pre-contract / cooling-off period",
            "rule_summary": (
                "Cancellation before contract exchange — full refund "
                "regardless of jurisdiction."
            ),
        }

    rule = _DEPOSIT_FORFEITURE_RULES.get(code, _DEFAULT_FORFEITURE_RULE)
    fraction, citation, summary = rule
    forfeited = (amount * fraction).quantize(Decimal("0.01"))
    refundable = (amount - forfeited).quantize(Decimal("0.01"))
    return {
        "jurisdiction": code or "—",
        "deposit_amount": amount,
        "forfeited_amount": forfeited,
        "refundable_amount": refundable,
        "rule_citation": citation,
        "rule_summary": summary,
    }


def supported_jurisdictions() -> list[str]:
    """Return the list of ISO-3166 alpha-2 codes with a real rule loaded."""
    return sorted(_DEPOSIT_FORFEITURE_RULES.keys())


# ── Residual development appraisal (RICS Red Book) ──────────────────────


def compute_residual_appraisal(
    gross_development_value: Decimal | float | int | str,
    construction_cost: Decimal | float | int | str,
    professional_fees_pct: Decimal | float | int | str = Decimal("10"),
    finance_cost: Decimal | float | int | str = Decimal("0"),
    sales_costs_pct: Decimal | float | int | str = Decimal("3"),
    developer_profit_target_pct: Decimal | float | int | str = Decimal("20"),
    contingency_pct: Decimal | float | int | str = Decimal("5"),
) -> dict[str, Any]:
    """Run the residual-valuation method (RICS Red Book — Global, 2025).

    Residual Land Value = GDV − (construction + fees + contingency +
    finance + sales costs + developer profit).

    Profit on Cost = developer_profit / total development cost, where
    "total development cost" is construction + fees + contingency +
    finance + sales costs (i.e. excluding the residual land value and
    excluding the profit line itself — the standard RICS denominator).
    Profit on GDV  = developer_profit / GDV.

    All inputs are coerced through ``Decimal`` so callers may pass floats
    or strings safely.  All percentages are in points (10 = 10%).

    Returns a dict with land value, profit metrics, and the cost breakdown
    so callers can render an itemised appraisal sheet.

    Pure: no DB / I/O.
    """
    gdv = Decimal(str(gross_development_value or 0))
    cc = Decimal(str(construction_cost or 0))
    pf_pct = Decimal(str(professional_fees_pct or 0))
    fin = Decimal(str(finance_cost or 0))
    sc_pct = Decimal(str(sales_costs_pct or 0))
    prof_pct = Decimal(str(developer_profit_target_pct or 0))
    cont_pct = Decimal(str(contingency_pct or 0))

    professional_fees = (cc * pf_pct / Decimal("100"))
    contingency = (cc * cont_pct / Decimal("100"))
    sales_costs = (gdv * sc_pct / Decimal("100"))
    developer_profit = (gdv * prof_pct / Decimal("100"))

    total_costs_excl_land = (
        cc + professional_fees + contingency + fin + sales_costs + developer_profit
    )
    residual_land_value = gdv - total_costs_excl_land

    q = Decimal("0.01")
    pct_q = Decimal("0.0001")
    total_dev_cost = cc + professional_fees + contingency + fin + sales_costs
    # Profit metrics use the developer-profit line as the numerator.
    profit_on_cost = (
        (developer_profit / total_dev_cost) if total_dev_cost > 0 else Decimal("0")
    )
    profit_on_gdv = (developer_profit / gdv) if gdv > 0 else Decimal("0")

    viable = residual_land_value >= 0

    return {
        "gdv": gdv.quantize(q),
        "construction_cost": cc.quantize(q),
        "professional_fees": professional_fees.quantize(q),
        "contingency": contingency.quantize(q),
        "finance_cost": fin.quantize(q),
        "sales_costs": sales_costs.quantize(q),
        "developer_profit": developer_profit.quantize(q),
        "total_costs_excl_land": total_costs_excl_land.quantize(q),
        "residual_land_value": residual_land_value.quantize(q),
        "profit_on_cost": profit_on_cost.quantize(pct_q),
        "profit_on_gdv": profit_on_gdv.quantize(pct_q),
        "viable": viable,
        "method": "RICS Red Book Global 2025 — Residual Valuation",
    }


def compute_sales_velocity(
    sold_units: int,
    total_units: int,
    months_on_market: Decimal | float | int | str,
) -> dict[str, Any]:
    """Return absorption / velocity metrics for a development.

    Velocity = sold_units / months_on_market  (units / month)
    Absorption_pct = sold_units / total_units * 100
    Months_to_sellout = (total_units − sold_units) / velocity

    Pure: no DB.
    """
    months = Decimal(str(months_on_market or 0))
    if total_units <= 0 or months <= 0:
        return {
            "velocity_units_per_month": Decimal("0"),
            "absorption_pct": Decimal("0"),
            "months_to_sellout": None,
            "sold_units": sold_units,
            "total_units": total_units,
        }
    velocity = Decimal(sold_units) / months
    absorption = (Decimal(sold_units) / Decimal(total_units)) * Decimal("100")
    remaining = total_units - sold_units
    months_to_sellout = (
        (Decimal(remaining) / velocity).quantize(Decimal("0.1"))
        if velocity > 0 and remaining > 0
        else (Decimal("0") if remaining == 0 else None)
    )
    return {
        "velocity_units_per_month": velocity.quantize(Decimal("0.01")),
        "absorption_pct": absorption.quantize(Decimal("0.01")),
        "months_to_sellout": months_to_sellout,
        "sold_units": sold_units,
        "total_units": total_units,
    }


# ── Service ─────────────────────────────────────────────────────────────


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


class PropertyDevService:
    """Business logic + workflow orchestration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.developments = DevelopmentRepository(session)
        self.house_types = HouseTypeRepository(session)
        self.variants = HouseTypeVariantRepository(session)
        self.plots = PlotRepository(session)
        self.option_groups = BuyerOptionGroupRepository(session)
        self.options = BuyerOptionRepository(session)
        self.buyers = BuyerRepository(session)
        self.selections = BuyerSelectionRepository(session)
        self.selection_items = BuyerSelectionItemRepository(session)
        self.handovers = HandoverRepository(session)
        self.handover_docs = HandoverDocRepository(session)
        self.snags = SnagRepository(session)
        self.warranty = WarrantyClaimRepository(session)
        self.pipeline = BuyerPipelineQueries(session)
        # ── R6 ─────────────────────────────────────────────────────
        self.leads = LeadRepository(session)
        self.reservations = ReservationRepository(session)
        self.sales_contracts = SalesContractRepository(session)
        self.sales_contract_revisions = SalesContractRevisionRepository(session)
        self.payment_schedules = PaymentScheduleRepository(session)
        self.instalments = InstalmentRepository(session)
        self.contract_parties = ContractPartyRepository(session)

    # ── Development ─────────────────────────────────────────────────────

    async def create_development(self, data: DevelopmentCreate) -> Development:
        obj = Development(
            project_id=data.project_id,
            code=data.code,
            name=data.name,
            location_address=data.location_address,
            total_plots=data.total_plots,
            sales_phase=data.sales_phase,
            launch_date=data.launch_date,
            completion_date=data.completion_date,
            marketing_brief=data.marketing_brief,
            status=data.status,
            units=data.units,
            metadata_=data.metadata,
        )
        return await self.developments.create(obj)

    async def get_development(self, dev_id: uuid.UUID) -> Development:
        obj = await self.developments.get_by_id(dev_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Development not found")
        return obj

    async def update_development(
        self, dev_id: uuid.UUID, data: DevelopmentUpdate
    ) -> Development:
        await self.get_development(dev_id)
        fields = _dump(data)
        await self.developments.update_fields(dev_id, **fields)
        return await self.get_development(dev_id)

    async def delete_development(self, dev_id: uuid.UUID) -> None:
        await self.get_development(dev_id)
        await self.developments.delete(dev_id)

    # ── House Type ──────────────────────────────────────────────────────

    async def create_house_type(self, data: HouseTypeCreate) -> HouseType:
        obj = HouseType(
            development_id=data.development_id,
            code=data.code,
            name=data.name,
            bedrooms=data.bedrooms,
            bathrooms=data.bathrooms,
            total_area_m2=data.total_area_m2,
            footprint_m2=data.footprint_m2,
            levels=data.levels,
            base_price=data.base_price,
            currency=data.currency,
            bim_model_ref=data.bim_model_ref,
            thumbnail_url=data.thumbnail_url,
            description=data.description,
            metadata_=data.metadata,
        )
        return await self.house_types.create(obj)

    async def get_house_type(self, ht_id: uuid.UUID) -> HouseType:
        obj = await self.house_types.get_by_id(ht_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="HouseType not found")
        return obj

    async def update_house_type(
        self, ht_id: uuid.UUID, data: HouseTypeUpdate
    ) -> HouseType:
        await self.get_house_type(ht_id)
        await self.house_types.update_fields(ht_id, **_dump(data))
        return await self.get_house_type(ht_id)

    async def delete_house_type(self, ht_id: uuid.UUID) -> None:
        await self.get_house_type(ht_id)
        await self.house_types.delete(ht_id)

    # ── Variant ─────────────────────────────────────────────────────────

    async def create_variant(
        self, data: HouseTypeVariantCreate
    ) -> HouseTypeVariant:
        obj = HouseTypeVariant(
            house_type_id=data.house_type_id,
            code=data.code,
            name=data.name,
            modifier_pct=data.modifier_pct,
            description=data.description,
            metadata_=data.metadata,
        )
        return await self.variants.create(obj)

    async def get_variant(self, v_id: uuid.UUID) -> HouseTypeVariant:
        obj = await self.variants.get_by_id(v_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Variant not found")
        return obj

    async def update_variant(
        self, v_id: uuid.UUID, data: HouseTypeVariantUpdate
    ) -> HouseTypeVariant:
        await self.get_variant(v_id)
        await self.variants.update_fields(v_id, **_dump(data))
        return await self.get_variant(v_id)

    async def delete_variant(self, v_id: uuid.UUID) -> None:
        await self.get_variant(v_id)
        await self.variants.delete(v_id)

    # ── Plot ────────────────────────────────────────────────────────────

    async def create_plot(self, data: PlotCreate) -> Plot:
        obj = Plot(
            development_id=data.development_id,
            plot_number=data.plot_number,
            house_type_id=data.house_type_id,
            house_type_variant_id=data.house_type_variant_id,
            orientation=data.orientation,
            area_m2=data.area_m2,
            garden_area_m2=data.garden_area_m2,
            price_base=data.price_base,
            currency=data.currency,
            status=data.status,
            reservation_deadline=data.reservation_deadline,
            construction_status_percent=data.construction_status_percent,
            metadata_=data.metadata,
        )
        return await self.plots.create(obj)

    async def get_plot(self, plot_id: uuid.UUID) -> Plot:
        obj = await self.plots.get_by_id(plot_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Plot not found")
        return obj

    async def update_plot(self, plot_id: uuid.UUID, data: PlotUpdate) -> Plot:
        plot = await self.get_plot(plot_id)
        fields = _dump(data)
        new_status = fields.get("status")
        if new_status:
            _ensure_transition(
                "plot", plot.status, new_status, allowed_plot_transitions
            )
        await self.plots.update_fields(plot_id, **fields)
        return await self.get_plot(plot_id)

    async def delete_plot(self, plot_id: uuid.UUID) -> None:
        await self.get_plot(plot_id)
        await self.plots.delete(plot_id)

    async def reserve_plot(
        self, plot_id: uuid.UUID, data: PlotReserveRequest
    ) -> tuple[Plot, Buyer]:
        """Reserve a plot for a buyer.

        Raises:
            HTTPException(409) if the plot is already reserved/sold.
        """
        plot = await self.get_plot(plot_id)
        if plot.status not in {"planned", "ready", "under_construction"}:
            raise HTTPException(
                status_code=409,
                detail=f"Plot in status '{plot.status}' cannot be reserved",
            )

        # The plot must not already be bound to a *different* buyer — the
        # ``Buyer.plot_id`` UNIQUE constraint would otherwise raise an
        # opaque IntegrityError at flush. Surface a clean 409 instead.
        existing_buyer = await self.buyers.get_for_plot(plot_id)
        if (
            existing_buyer is not None
            and data.buyer_id is not None
            and existing_buyer.id != data.buyer_id
        ) or (existing_buyer is not None and data.buyer_id is None):
            raise HTTPException(
                status_code=409,
                detail="Plot is already assigned to a buyer",
            )

        # Bind / create buyer.
        if data.buyer_id is not None:
            buyer = await self.buyers.get_by_id(data.buyer_id)
            if buyer is None:
                raise HTTPException(status_code=404, detail="Buyer not found")
            # No cross-development binding: a buyer can only be placed on a
            # plot inside their own development (IDOR / data-integrity).
            if buyer.development_id != plot.development_id:
                raise HTTPException(
                    status_code=409,
                    detail="Buyer belongs to a different development",
                )
            # Terminal/contracted buyers must not be silently re-pointed at
            # a new plot — only leads/reserved buyers may be (re)reserved.
            if buyer.status not in {"lead", "reserved"}:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Buyer in status '{buyer.status}' cannot reserve a plot"
                    ),
                )
            # If the buyer was reserved against another plot, release that
            # plot back to ``planned`` so it does not stay orphaned in
            # ``reserved`` with no buyer attached.
            if buyer.plot_id is not None and buyer.plot_id != plot_id:
                old_plot = await self.plots.get_by_id(buyer.plot_id)
                if old_plot is not None and old_plot.status == "reserved":
                    await self.plots.update_fields(
                        buyer.plot_id, status="planned", reservation_deadline=None
                    )
            await self.buyers.update_fields(
                buyer.id, plot_id=plot_id, status="reserved"
            )
            buyer = await self.buyers.get_by_id(buyer.id)
        else:
            buyer = Buyer(
                development_id=plot.development_id,
                plot_id=plot_id,
                full_name=data.full_name,
                email=data.email,
                phone=data.phone,
                language=data.language,
                status="reserved",
                metadata_=data.metadata,
            )
            buyer = await self.buyers.create(buyer)

        # Flip plot.
        await self.plots.update_fields(
            plot_id,
            status="reserved",
            reservation_deadline=data.reservation_deadline,
        )
        plot = await self.get_plot(plot_id)

        return plot, buyer

    # ── Option Group / Option ───────────────────────────────────────────

    async def create_option_group(
        self, data: BuyerOptionGroupCreate
    ) -> BuyerOptionGroup:
        obj = BuyerOptionGroup(
            development_id=data.development_id,
            code=data.code,
            name=data.name,
            group_type=data.group_type,
            display_order=data.display_order,
            allow_multiple=data.allow_multiple,
            max_count=data.max_count,
            freeze_offset_days_before_handover=data.freeze_offset_days_before_handover,
            metadata_=data.metadata,
        )
        return await self.option_groups.create(obj)

    async def get_option_group(self, g_id: uuid.UUID) -> BuyerOptionGroup:
        obj = await self.option_groups.get_by_id(g_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="OptionGroup not found")
        return obj

    async def update_option_group(
        self, g_id: uuid.UUID, data: BuyerOptionGroupUpdate
    ) -> BuyerOptionGroup:
        await self.get_option_group(g_id)
        await self.option_groups.update_fields(g_id, **_dump(data))
        return await self.get_option_group(g_id)

    async def delete_option_group(self, g_id: uuid.UUID) -> None:
        await self.get_option_group(g_id)
        await self.option_groups.delete(g_id)

    async def create_option(self, data: BuyerOptionCreate) -> BuyerOption:
        obj = BuyerOption(
            group_id=data.group_id,
            code=data.code,
            name=data.name,
            sku=data.sku,
            price_delta=data.price_delta,
            currency=data.currency,
            lead_time_days=data.lead_time_days,
            supplier_name=data.supplier_name,
            thumbnail_url=data.thumbnail_url,
            is_active=data.is_active,
            compatibility_rules=data.compatibility_rules,
            metadata_=data.metadata,
        )
        return await self.options.create(obj)

    async def get_option(self, o_id: uuid.UUID) -> BuyerOption:
        obj = await self.options.get_by_id(o_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Option not found")
        return obj

    async def update_option(
        self, o_id: uuid.UUID, data: BuyerOptionUpdate
    ) -> BuyerOption:
        await self.get_option(o_id)
        await self.options.update_fields(o_id, **_dump(data))
        return await self.get_option(o_id)

    async def delete_option(self, o_id: uuid.UUID) -> None:
        await self.get_option(o_id)
        await self.options.delete(o_id)

    # ── Buyer ───────────────────────────────────────────────────────────

    async def create_buyer(self, data: BuyerCreate) -> Buyer:
        obj = Buyer(
            development_id=data.development_id,
            plot_id=data.plot_id,
            portal_user_id=data.portal_user_id,
            full_name=data.full_name,
            email=data.email,
            phone=data.phone,
            language=data.language,
            status=data.status,
            contract_value=data.contract_value,
            currency=data.currency,
            metadata_=data.metadata,
        )
        return await self.buyers.create(obj)

    async def get_buyer(self, b_id: uuid.UUID) -> Buyer:
        obj = await self.buyers.get_by_id(b_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Buyer not found")
        return obj

    async def update_buyer(self, b_id: uuid.UUID, data: BuyerUpdate) -> Buyer:
        buyer = await self.get_buyer(b_id)
        fields = _dump(data)
        new_status = fields.get("status")
        if new_status:
            _ensure_transition(
                "buyer", buyer.status, new_status, allowed_buyer_transitions
            )
        # plot_id consistency: if the caller sets plot_id, it must belong
        # to the same development. Closes a cross-development link bug
        # caught by task #134's plot-collision test. ``None`` is allowed
        # (un-assign the plot).
        plot_field_provided = "plot_id" in fields
        if plot_field_provided and fields["plot_id"] is not None:
            target_plot = await self.plots.get_by_id(fields["plot_id"])
            if target_plot is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Plot {fields['plot_id']} not found",
                )
            if target_plot.development_id != buyer.development_id:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Plot belongs to a different development "
                        f"({target_plot.development_id})"
                    ),
                )
        # Normalise jurisdiction (ISO-3166 alpha-2) to upper-case so the
        # deposit-forfeiture rule lookup stays case-insensitive.
        if "jurisdiction" in fields and isinstance(fields["jurisdiction"], str):
            fields["jurisdiction"] = fields["jurisdiction"].upper()
        # Currency: enforce 3-letter ISO format when supplied (the schema
        # only caps length at 8 to allow stablecoin tickers like USDT —
        # for the edit flow we want a real currency, not a tag).
        currency = fields.get("currency")
        if currency is not None and currency != "" and len(currency) != 3:
            raise HTTPException(
                status_code=422,
                detail="Currency must be a 3-letter ISO code",
            )
        await self.buyers.update_fields(b_id, **fields)
        return await self.get_buyer(b_id)

    async def delete_buyer(self, b_id: uuid.UUID) -> None:
        await self.get_buyer(b_id)
        await self.buyers.delete(b_id)

    async def convert_buyer_to_contracted(
        self, buyer_id: uuid.UUID, data: BuyerContractRequest
    ) -> Buyer:
        """Walk a buyer up the lead → reserved → contracted path."""
        buyer = await self.get_buyer(buyer_id)
        if buyer.status == "lead":
            _ensure_transition(
                "buyer", buyer.status, "reserved", allowed_buyer_transitions
            )
            await self.buyers.update_fields(buyer_id, status="reserved")
            buyer.status = "reserved"
        _ensure_transition(
            "buyer", buyer.status, "contracted", allowed_buyer_transitions
        )

        fields: dict[str, Any] = {
            "status": "contracted",
            "contract_value": data.contract_value,
            "currency": data.currency,
            "contract_signed_at": data.contract_signed_at,
            "deposit_paid_at": data.deposit_paid_at,
            "freeze_deadline": data.freeze_deadline,
        }
        if data.deposit_amount is not None:
            fields["deposit_amount"] = data.deposit_amount
        if data.jurisdiction:
            fields["jurisdiction"] = data.jurisdiction.upper()
        await self.buyers.update_fields(buyer_id, **fields)
        contracted = await self.get_buyer(buyer_id)

        event_bus.publish_detached(
            "property_dev.buyer.contracted",
            data={
                "buyer_id": str(buyer_id),
                "development_id": str(contracted.development_id),
                "plot_id": str(contracted.plot_id) if contracted.plot_id else None,
                "contract_value": str(contracted.contract_value),
                "currency": contracted.currency,
                "contract_signed_at": contracted.contract_signed_at,
                "deposit_amount": str(getattr(contracted, "deposit_amount", 0) or 0),
                "jurisdiction": getattr(contracted, "jurisdiction", "") or "",
            },
            source_module="property_dev",
        )

        return contracted

    async def cancel_buyer(
        self, buyer_id: uuid.UUID, data: BuyerCancelRequest
    ) -> tuple[Buyer, dict[str, Any]]:
        """Cancel a buyer and compute deposit forfeiture per jurisdiction.

        Returns ``(buyer, forfeiture_breakdown)``. Updates the buyer's
        ``status='cancelled'`` + ``cancelled_at`` + ``cancelled_reason``
        and persists ``deposit_forfeited`` / ``deposit_refunded`` columns.
        Publishes ``property_dev.buyer.cancelled`` event.

        Raises:
            HTTPException(409) if the buyer is already cancelled or
            already completed (terminal states).
        """
        buyer = await self.get_buyer(buyer_id)
        if buyer.status in {"cancelled", "completed"}:
            raise HTTPException(
                status_code=409,
                detail=f"Buyer in status '{buyer.status}' cannot be cancelled",
            )

        # Pre-contract cancellations get full refund regardless of jurisdiction.
        cancelled_pre_contract = buyer.status in {"lead", "reserved"}
        jurisdiction = (
            data.jurisdiction_override.upper()
            if data.jurisdiction_override
            else (buyer.jurisdiction or "")
        )
        forfeiture = compute_deposit_forfeiture(
            buyer.deposit_amount or Decimal("0"),
            jurisdiction,
            cancelled_before_contract=cancelled_pre_contract,
        )

        await self.buyers.update_fields(
            buyer_id,
            status="cancelled",
            cancelled_at=data.cancelled_at,
            cancelled_reason=data.reason,
            deposit_forfeited=forfeiture["forfeited_amount"],
            deposit_refunded=forfeiture["refundable_amount"],
        )
        # Free up the plot if it was held by this buyer. A merely
        # ``reserved`` plot goes back to ``planned`` (re-marketable, no
        # construction state to preserve). A ``sold`` plot has typically
        # been (part-)built, so it is released to ``ready`` rather than
        # regressed all the way to ``planned`` — that keeps the legal
        # plot state machine intact (``sold`` -> ``planned`` is NOT an
        # allowed transition) and does not throw away build progress.
        if buyer.plot_id:
            plot = await self.plots.get_by_id(buyer.plot_id)
            if plot is not None and plot.status == "reserved":
                await self.plots.update_fields(
                    buyer.plot_id, status="planned", reservation_deadline=None
                )
            elif plot is not None and plot.status == "sold":
                await self.plots.update_fields(buyer.plot_id, status="ready")

        cancelled = await self.get_buyer(buyer_id)
        event_bus.publish_detached(
            "property_dev.buyer.cancelled",
            data={
                "buyer_id": str(buyer_id),
                "development_id": str(cancelled.development_id),
                "plot_id": str(cancelled.plot_id) if cancelled.plot_id else None,
                "deposit_forfeited": str(forfeiture["forfeited_amount"]),
                "deposit_refunded": str(forfeiture["refundable_amount"]),
                "rule_citation": forfeiture["rule_citation"],
            },
            source_module="property_dev",
        )
        forfeiture["buyer_id"] = buyer_id  # type: ignore[index]
        return cancelled, forfeiture

    # ── Selection ───────────────────────────────────────────────────────

    async def create_selection(
        self, data: BuyerSelectionCreate
    ) -> BuyerSelection:
        obj = BuyerSelection(
            buyer_id=data.buyer_id,
            status=data.status,
            notes=data.notes,
            metadata_=data.metadata,
        )
        return await self.selections.create(obj)

    async def get_selection(self, s_id: uuid.UUID) -> BuyerSelection:
        obj = await self.selections.get_by_id(s_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Selection not found")
        return obj

    async def update_selection(
        self, s_id: uuid.UUID, data: BuyerSelectionUpdate
    ) -> BuyerSelection:
        sel = await self.get_selection(s_id)
        fields = _dump(data)
        new_status = fields.get("status")
        if new_status:
            _ensure_transition(
                "selection", sel.status, new_status, allowed_selection_transitions
            )
        await self.selections.update_fields(s_id, **fields)
        return await self.get_selection(s_id)

    async def delete_selection(self, s_id: uuid.UUID) -> None:
        await self.get_selection(s_id)
        await self.selections.delete(s_id)

    async def add_selection_item(
        self, selection_id: uuid.UUID, data: BuyerSelectionItemCreate
    ) -> BuyerSelectionItem:
        sel = await self.get_selection(selection_id)
        if sel.status in {"locked", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Selection is {sel.status}",
            )
        option = await self.get_option(data.option_id)
        if not option.is_active:
            raise HTTPException(
                status_code=409,
                detail="Option is no longer available",
            )
        unit_price = (
            data.unit_price_snapshot
            if data.unit_price_snapshot is not None
            else option.price_delta
        )
        item = BuyerSelectionItem(
            selection_id=selection_id,
            option_id=data.option_id,
            quantity=data.quantity,
            unit_price_snapshot=unit_price,
            total_price=Decimal(str(unit_price)) * Decimal(str(data.quantity)),
            included_in_production=False,
            metadata_=data.metadata,
        )
        item = await self.selection_items.create(item)
        item_id = item.id
        # ``_recompute_selection_total`` calls ``update_fields`` which runs
        # ``session.expire_all()`` — that expires the freshly-created ``item``
        # too, so returning it would force a lazy-load outside the async
        # session (MissingGreenlet 500). Re-fetch after recompute so the
        # router serialises a live, attribute-populated instance.
        await self._recompute_selection_total(selection_id)
        refreshed = await self.selection_items.get_by_id(item_id)
        return refreshed if refreshed is not None else item

    async def remove_selection_item(self, item_id: uuid.UUID) -> None:
        item = await self.selection_items.get_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Selection item not found")
        sel = await self.get_selection(item.selection_id)
        if sel.status in {"locked", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Selection is {sel.status}",
            )
        await self.selection_items.delete(item_id)
        await self._recompute_selection_total(item.selection_id)

    async def _recompute_selection_total(
        self, selection_id: uuid.UUID
    ) -> Decimal:
        items = await self.selection_items.list_for_selection(selection_id)
        total = compute_buyer_selection_total(items)
        await self.selections.update_fields(
            selection_id, total_options_value=total
        )
        return total

    async def submit_selection(self, selection_id: uuid.UUID) -> BuyerSelection:
        sel = await self.get_selection(selection_id)
        _ensure_transition(
            "selection", sel.status, "submitted", allowed_selection_transitions
        )
        await self.selections.update_fields(
            selection_id, status="submitted", submitted_at=_today_iso()
        )
        return await self.get_selection(selection_id)

    async def lock_selection(self, selection_id: uuid.UUID) -> BuyerSelection:
        """Lock a selection (typically after deposit + design freeze)."""
        sel = await self.get_selection(selection_id)
        # Allow lock from draft or submitted.
        if sel.status == "locked":
            return sel
        if sel.status not in {"draft", "submitted"}:
            _ensure_transition(
                "selection", sel.status, "locked", allowed_selection_transitions
            )
        await self.selections.update_fields(
            selection_id, status="locked", locked_at=_today_iso()
        )
        locked = await self.get_selection(selection_id)
        event_bus.publish_detached(
            "property_dev.selection.locked",
            data={
                "selection_id": str(selection_id),
                "buyer_id": str(locked.buyer_id),
                "total_options_value": str(locked.total_options_value),
                "locked_at": locked.locked_at,
            },
            source_module="property_dev",
        )
        return locked

    async def submit_for_production(
        self, buyer_id: uuid.UUID
    ) -> BuyerSelection:
        """Flag every line in the buyer's locked selection as
        ``included_in_production`` so downstream procurement can pick it up.
        """
        buyer = await self.get_buyer(buyer_id)
        sel = await self.selections.current_selection_for_buyer(buyer_id)
        if sel is None:
            raise HTTPException(
                status_code=404, detail="No selection for buyer"
            )
        if sel.status != "locked":
            raise HTTPException(
                status_code=409,
                detail="Selection must be locked before production handoff",
            )
        items = await self.selection_items.list_for_selection(sel.id)
        for item in items:
            await self.selection_items.update_fields(
                item.id, included_in_production=True
            )

        event_bus.publish_detached(
            "property_dev.selection.submitted_for_production",
            data={
                "selection_id": str(sel.id),
                "buyer_id": str(buyer_id),
                "development_id": str(buyer.development_id),
                "plot_id": str(buyer.plot_id) if buyer.plot_id else None,
                "total_options_value": str(sel.total_options_value),
                "item_count": len(items),
            },
            source_module="property_dev",
        )
        return sel

    # ── Handover ────────────────────────────────────────────────────────

    async def create_handover(self, data: HandoverCreate) -> Handover:
        obj = Handover(
            plot_id=data.plot_id,
            scheduled_at=data.scheduled_at,
            notes=data.notes,
            metadata_=data.metadata,
        )
        return await self.handovers.create(obj)

    async def get_handover(self, h_id: uuid.UUID) -> Handover:
        obj = await self.handovers.get_by_id(h_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Handover not found")
        return obj

    async def update_handover(
        self, h_id: uuid.UUID, data: HandoverUpdate
    ) -> Handover:
        await self.get_handover(h_id)
        await self.handovers.update_fields(h_id, **_dump(data))
        return await self.get_handover(h_id)

    async def delete_handover(self, h_id: uuid.UUID) -> None:
        await self.get_handover(h_id)
        await self.handovers.delete(h_id)

    async def complete_handover(
        self, h_id: uuid.UUID, data: HandoverCompleteRequest
    ) -> Handover:
        handover = await self.get_handover(h_id)
        if handover.completed_at:
            return handover
        await self.handovers.update_fields(
            h_id,
            completed_at=data.completed_at,
            customer_signature_ref=data.customer_signature_ref,
            keys_handed_over_at=data.keys_handed_over_at or data.completed_at,
            final_check_passed=data.final_check_passed,
            snag_count_at_handover=data.snag_count_at_handover,
            notes=data.notes if data.notes is not None else handover.notes,
        )

        # Flip plot to handed_over.
        await self.plots.update_fields(handover.plot_id, status="handed_over")

        # Advance the linked buyer to ``completed``. Without this the buyer
        # is stuck at ``contracted`` forever even after the keys are handed
        # over, so ``buyers_by_status`` / ``revenue_completed`` and the
        # buyer-stage UI never reflect a finished sale. The transition is
        # only legal from ``contracted`` (per ``_BUYER_TRANSITIONS``); any
        # other state (lead/reserved/cancelled) is left untouched.
        buyer_completed = False
        buyer = await self.buyers.get_for_plot(handover.plot_id)
        if buyer is not None and buyer.status == "contracted":
            await self.buyers.update_fields(buyer.id, status="completed")
            buyer_completed = True

        completed = await self.get_handover(h_id)
        event_bus.publish_detached(
            "property_dev.handover.completed",
            data={
                "handover_id": str(h_id),
                "plot_id": str(completed.plot_id),
                "completed_at": completed.completed_at,
                "snag_count": completed.snag_count_at_handover,
                "final_check_passed": completed.final_check_passed,
                "buyer_id": str(buyer.id) if buyer is not None else None,
                "buyer_completed": buyer_completed,
            },
            source_module="property_dev",
        )
        return completed

    # ── Snag ────────────────────────────────────────────────────────────

    async def create_snag(self, data: SnagCreate) -> Snag:
        obj = Snag(
            handover_id=data.handover_id,
            location_in_plot=data.location_in_plot,
            severity=data.severity,
            description=data.description,
            status=data.status,
            reported_at=data.reported_at or _today_iso(),
            metadata_=data.metadata,
        )
        return await self.snags.create(obj)

    async def get_snag(self, s_id: uuid.UUID) -> Snag:
        obj = await self.snags.get_by_id(s_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Snag not found")
        return obj

    async def update_snag(self, s_id: uuid.UUID, data: SnagUpdate) -> Snag:
        await self.get_snag(s_id)
        await self.snags.update_fields(s_id, **_dump(data))
        return await self.get_snag(s_id)

    async def delete_snag(self, s_id: uuid.UUID) -> None:
        await self.get_snag(s_id)
        await self.snags.delete(s_id)

    async def mark_snag_fixed(
        self, s_id: uuid.UUID, *, fix_notes: str | None = None
    ) -> Snag:
        snag = await self.get_snag(s_id)
        if snag.status == "fixed":
            return snag
        await self.snags.update_fields(
            s_id, status="fixed", fixed_at=_today_iso(), fix_notes=fix_notes
        )
        return await self.get_snag(s_id)

    async def mark_snag_wont_fix(
        self, s_id: uuid.UUID, *, fix_notes: str | None = None
    ) -> Snag:
        await self.get_snag(s_id)
        await self.snags.update_fields(
            s_id, status="wont_fix", fix_notes=fix_notes
        )
        return await self.get_snag(s_id)

    # ── Warranty ────────────────────────────────────────────────────────

    async def raise_warranty_claim(
        self, plot_id: uuid.UUID, buyer_id: uuid.UUID, data: WarrantyClaimCreate
    ) -> WarrantyClaim:
        obj = WarrantyClaim(
            plot_id=plot_id,
            buyer_id=buyer_id,
            raised_at=data.raised_at or _today_iso(),
            category=data.category,
            description=data.description,
            status="raised",
            linked_service_ticket_id=data.linked_service_ticket_id,
            metadata_=data.metadata,
        )
        claim = await self.warranty.create(obj)
        event_bus.publish_detached(
            "property_dev.warranty.raised",
            data={
                "claim_id": str(claim.id),
                "plot_id": str(plot_id),
                "buyer_id": str(buyer_id),
                "category": data.category,
                "description": data.description[:200],
            },
            source_module="property_dev",
        )
        return claim

    async def get_warranty(self, w_id: uuid.UUID) -> WarrantyClaim:
        obj = await self.warranty.get_by_id(w_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="WarrantyClaim not found")
        return obj

    async def update_warranty(
        self, w_id: uuid.UUID, data: WarrantyClaimUpdate
    ) -> WarrantyClaim:
        claim = await self.get_warranty(w_id)
        fields = _dump(data)
        new_status = fields.get("status")
        if new_status:
            _ensure_transition(
                "warranty", claim.status, new_status, allowed_warranty_transitions
            )
        await self.warranty.update_fields(w_id, **fields)
        return await self.get_warranty(w_id)

    async def delete_warranty(self, w_id: uuid.UUID) -> None:
        await self.get_warranty(w_id)
        await self.warranty.delete(w_id)

    async def warranty_accept(self, w_id: uuid.UUID) -> WarrantyClaim:
        claim = await self.get_warranty(w_id)
        _ensure_transition(
            "warranty", claim.status, "accepted", allowed_warranty_transitions
        )
        await self.warranty.update_fields(
            w_id, status="accepted", accepted_at=_today_iso()
        )
        return await self.get_warranty(w_id)

    async def warranty_reject(self, w_id: uuid.UUID) -> WarrantyClaim:
        claim = await self.get_warranty(w_id)
        _ensure_transition(
            "warranty", claim.status, "rejected", allowed_warranty_transitions
        )
        await self.warranty.update_fields(w_id, status="rejected")
        return await self.get_warranty(w_id)

    async def warranty_close(self, w_id: uuid.UUID) -> WarrantyClaim:
        claim = await self.get_warranty(w_id)
        _ensure_transition(
            "warranty", claim.status, "closed", allowed_warranty_transitions
        )
        await self.warranty.update_fields(
            w_id, status="closed", closed_at=_today_iso()
        )
        return await self.get_warranty(w_id)

    # ── Dashboards ──────────────────────────────────────────────────────

    async def development_sales_dashboard(
        self, dev_id: uuid.UUID
    ) -> dict[str, Any]:
        dev = await self.get_development(dev_id)
        plots_by_status = await self.plots.count_for_development_by_status(dev_id)
        buyers_by_status = await self.buyers.count_for_development_by_status(dev_id)
        contracted_value = await self.buyers.sum_contract_value(
            dev_id, status_in=["contracted", "completed"]
        )
        open_snags = await self.snags.count_open_for_development(dev_id)
        open_warranty = await self.warranty.count_open_for_development(dev_id)
        completed_handovers, scheduled_handovers = (
            await self.handovers.count_progress_for_development(dev_id)
        )
        total_plots = sum(plots_by_status.values()) or 0
        sold = plots_by_status.get("sold", 0) + plots_by_status.get(
            "handed_over", 0
        )
        sell_through = (
            Decimal(sold) / Decimal(total_plots) * Decimal("100")
            if total_plots
            else Decimal("0")
        )
        return {
            "development_id": dev.id,
            "total_plots": total_plots,
            "plots_by_status": plots_by_status,
            "buyers_by_status": buyers_by_status,
            "contracted_value": Decimal(str(contracted_value or 0)),
            "open_snags": open_snags,
            "open_warranty_claims": open_warranty,
            "completed_handovers": completed_handovers,
            "scheduled_handovers": scheduled_handovers,
            "sell_through_percent": sell_through.quantize(Decimal("0.01")),
        }

    # ── Handover docs ───────────────────────────────────────────────────

    async def create_handover_doc(
        self, data: HandoverDocCreate
    ) -> HandoverDoc:
        await self.get_handover(data.handover_id)
        obj = HandoverDoc(
            handover_id=data.handover_id,
            doc_type=data.doc_type,
            title=data.title,
            file_url=data.file_url,
            is_required=data.is_required,
            is_delivered=data.is_delivered,
            delivered_at=_today_iso() if data.is_delivered else None,
            metadata_=data.metadata,
        )
        return await self.handover_docs.create(obj)

    async def get_handover_doc(self, doc_id: uuid.UUID) -> HandoverDoc:
        obj = await self.handover_docs.get_by_id(doc_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="HandoverDoc not found")
        return obj

    async def update_handover_doc(
        self, doc_id: uuid.UUID, data: HandoverDocUpdate
    ) -> HandoverDoc:
        doc = await self.get_handover_doc(doc_id)
        fields = _dump(data)
        # Stamp delivered_at when flipping is_delivered → True.
        if fields.get("is_delivered") is True and not doc.is_delivered:
            fields["delivered_at"] = _today_iso()
        if fields.get("is_delivered") is False:
            fields["delivered_at"] = None
        await self.handover_docs.update_fields(doc_id, **fields)
        return await self.get_handover_doc(doc_id)

    async def delete_handover_doc(self, doc_id: uuid.UUID) -> None:
        await self.get_handover_doc(doc_id)
        await self.handover_docs.delete(doc_id)

    async def handover_bundle(self, handover_id: uuid.UUID) -> dict[str, Any]:
        """Return all handover docs + required-doc compliance status."""
        await self.get_handover(handover_id)
        docs = await self.handover_docs.list_for_handover(handover_id)
        required = [d for d in docs if d.is_required]
        missing = [d.doc_type for d in required if not d.is_delivered]
        return {
            "handover_id": handover_id,
            "docs": docs,
            "delivered_count": sum(1 for d in docs if d.is_delivered),
            "required_count": len(required),
            "missing_required": missing,
            "ready_for_handover": not missing,
        }

    # ── Sales pipeline kanban + reservation calendar ────────────────────

    async def sales_kanban(self, dev_id: uuid.UUID) -> dict[str, Any]:
        """Group buyers into kanban columns by status."""
        await self.get_development(dev_id)
        rows = await self.pipeline.kanban_for_development(dev_id)
        # Stable column order for the UI.
        column_order = ("lead", "reserved", "contracted", "completed", "cancelled")
        columns: dict[str, dict[str, Any]] = {
            s: {"status": s, "buyers": [], "count": 0, "total_value": Decimal("0")}
            for s in column_order
        }
        for buyer, plot in rows:
            col = columns.setdefault(
                buyer.status,
                {"status": buyer.status, "buyers": [], "count": 0,
                 "total_value": Decimal("0")},
            )
            col["buyers"].append(
                {
                    "buyer_id": buyer.id,
                    "full_name": buyer.full_name,
                    "email": buyer.email,
                    "plot_id": buyer.plot_id,
                    "plot_number": plot.plot_number if plot is not None else None,
                    "status": buyer.status,
                    "contract_value": Decimal(str(buyer.contract_value or 0)),
                    "currency": buyer.currency,
                    "contract_signed_at": buyer.contract_signed_at,
                    "freeze_deadline": buyer.freeze_deadline,
                }
            )
            col["count"] += 1
            col["total_value"] += Decimal(str(buyer.contract_value or 0))
        return {
            "development_id": dev_id,
            "columns": list(columns.values()),
        }

    async def reservation_calendar(
        self,
        dev_id: uuid.UUID,
        period_start: str,
        period_end: str,
    ) -> dict[str, Any]:
        """Upcoming reservation + freeze + contract deadlines."""
        await self.get_development(dev_id)
        rows = await self.pipeline.reservation_calendar(
            dev_id, period_start, period_end,
        )
        entries: list[dict[str, Any]] = []
        for plot, buyer in rows:
            entries.append(
                {
                    "plot_id": plot.id,
                    "plot_number": plot.plot_number,
                    "buyer_id": buyer.id if buyer else None,
                    "buyer_name": buyer.full_name if buyer else "",
                    "reservation_deadline": plot.reservation_deadline,
                    "freeze_deadline": buyer.freeze_deadline if buyer else None,
                    "status": plot.status,
                }
            )
        return {
            "development_id": dev_id,
            "period_start": period_start,
            "period_end": period_end,
            "entries": entries,
        }

    async def development_pnl(self, dev_id: uuid.UUID) -> dict[str, Any]:
        """Aggregate revenue + deposit + warranty for a development.

        Cost data comes from finance via cross-module events; here we
        report the developer-visible revenue + deposit + after-care
        metrics.

        Currency: a development is single-currency by convention. We pick
        the currency of the first buyer that has one and only aggregate
        buyers in that currency — silently summing mixed-currency contract
        values into one number is meaningless. ``mixed_currency`` flags
        when at least one buyer used a different currency so the UI can
        warn instead of showing a wrong total.
        """
        dev = await self.get_development(dev_id)
        rows = await self.pipeline.kanban_for_development(dev_id)
        currency = ""
        for buyer, _plot in rows:
            if buyer.currency:
                currency = buyer.currency
                break
        mixed_currency = False
        revenue_contracted = Decimal("0")
        revenue_completed = Decimal("0")
        deposits_held = Decimal("0")
        deposits_forfeited = Decimal("0")
        plot_count_sold = 0
        plot_count_handed_over = 0
        contract_revenue_total = Decimal("0")
        contract_buyer_count = 0
        for buyer, plot in rows:
            b_ccy = buyer.currency or ""
            # Only aggregate money for buyers in the development currency.
            # A buyer with no currency set carries no monetary signal so
            # it is treated as in-currency (its value is 0 anyway).
            in_currency = (not b_ccy) or (not currency) or (b_ccy == currency)
            if b_ccy and currency and b_ccy != currency:
                mixed_currency = True
            value = Decimal(str(buyer.contract_value or 0))
            if in_currency:
                if buyer.status == "contracted":
                    revenue_contracted += value
                if buyer.status == "completed":
                    revenue_completed += value
                if buyer.status in {"contracted", "completed"} and value > 0:
                    contract_revenue_total += value
                    contract_buyer_count += 1
                if buyer.status in {"reserved", "contracted"}:
                    deposits_held += Decimal(str(buyer.deposit_amount or 0))
                deposits_forfeited += Decimal(
                    str(buyer.deposit_forfeited or 0)
                )
            if plot is not None and plot.status == "sold":
                plot_count_sold += 1
            if plot is not None and plot.status == "handed_over":
                plot_count_handed_over += 1
        # Average sale price = mean contract value across buyers that
        # actually hold a contract — NOT contracted revenue divided by
        # the count of *sold plots* (mismatched populations: a contracted
        # buyer's plot is usually still under construction, not "sold").
        avg_sale = (
            (contract_revenue_total / Decimal(contract_buyer_count))
            .quantize(Decimal("0.01"))
            if contract_buyer_count else Decimal("0")
        )
        open_warranty = await self.warranty.count_open_for_development(dev_id)
        open_snags = await self.snags.count_open_for_development(dev_id)
        return {
            "development_id": dev.id,
            "currency": currency,
            "mixed_currency": mixed_currency,
            "revenue_contracted": revenue_contracted.quantize(Decimal("0.01")),
            "revenue_completed": revenue_completed.quantize(Decimal("0.01")),
            "deposits_held": deposits_held.quantize(Decimal("0.01")),
            "deposits_forfeited": deposits_forfeited.quantize(Decimal("0.01")),
            "plot_count_sold": plot_count_sold,
            "plot_count_handed_over": plot_count_handed_over,
            "avg_sale_price": avg_sale,
            "open_warranty_count": open_warranty,
            "open_snag_count": open_snags,
        }


    # ════════════════════════════════════════════════════════════════════
    # R6 — Lead / Reservation / SPA / PaymentSchedule / ContractParty
    # ════════════════════════════════════════════════════════════════════

    # ── Lead ────────────────────────────────────────────────────────────

    async def create_lead(self, data: LeadCreate) -> Lead:
        """Create a new lead at the top of the funnel."""
        if data.preferred_house_type_id is not None:
            ht = await self.house_types.get_by_id(data.preferred_house_type_id)
            if ht is None:
                raise HTTPException(
                    status_code=422, detail="preferred_house_type not found"
                )
        if data.development_id is not None:
            dev = await self.developments.get_by_id(data.development_id)
            if dev is None:
                raise HTTPException(
                    status_code=422, detail="development not found"
                )
        obj = Lead(
            development_id=data.development_id,
            tenant_id=data.tenant_id,
            source=data.source,
            lead_score=data.lead_score,
            assigned_agent_user_id=data.assigned_agent_user_id,
            status=data.status,
            nurture_stage=data.nurture_stage,
            full_name=data.full_name,
            email=data.email,
            phone=data.phone,
            language=data.language,
            budget_min=data.budget_min,
            budget_max=data.budget_max,
            currency=data.currency or "",
            preferred_house_type_id=data.preferred_house_type_id,
            notes=data.notes,
            metadata_=data.metadata,
        )
        lead = await self.leads.create(obj)
        event_bus.publish_detached(
            "property_dev.lead.created",
            data={
                "lead_id": str(lead.id),
                "development_id": (
                    str(lead.development_id) if lead.development_id else None
                ),
                "source": lead.source,
                "status": lead.status,
                "email": lead.email,
            },
            source_module="property_dev",
        )
        return lead

    async def get_lead(self, lead_id: uuid.UUID) -> Lead:
        obj = await self.leads.get_by_id(lead_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return obj

    async def update_lead(
        self, lead_id: uuid.UUID, data: LeadUpdate
    ) -> Lead:
        lead = await self.get_lead(lead_id)
        fields = _dump(data)
        new_status = fields.get("status")
        if new_status:
            _ensure_transition(
                "lead", lead.status, new_status, allowed_lead_transitions
            )
        await self.leads.update_fields(lead_id, **fields)
        return await self.get_lead(lead_id)

    async def delete_lead(self, lead_id: uuid.UUID) -> None:
        await self.get_lead(lead_id)
        await self.leads.delete(lead_id)

    async def convert_lead_to_reservation(
        self,
        lead_id: uuid.UUID,
        data: LeadConvertToReservationRequest,
    ) -> Reservation:
        """Convert a Lead → Reservation (+ optionally a Buyer shadow).

        Publishes ``property_dev.lead.converted``.

        Raises:
            HTTPException(409) if the lead is in a terminal state.
            HTTPException(422) if plot is missing or doesn't accept new
                reservations (status='sold' or 'handed_over').
        """
        lead = await self.get_lead(lead_id)
        if lead.status in {"converted", "lost", "disqualified"}:
            raise HTTPException(
                status_code=409,
                detail=f"Lead in status '{lead.status}' cannot convert",
            )
        plot = await self.plots.get_by_id(data.plot_id)
        if plot is None:
            raise HTTPException(status_code=422, detail="plot not found")
        if plot.status in {"sold", "handed_over"}:
            raise HTTPException(
                status_code=409,
                detail=f"Plot {plot.plot_number} not available for reservation",
            )

        # Optionally materialise a Buyer shadow.
        buyer: Buyer | None = None
        if data.create_buyer:
            dev_id = lead.development_id or plot.development_id
            buyer_obj = Buyer(
                development_id=dev_id,
                plot_id=plot.id,
                full_name=lead.full_name,
                email=lead.email,
                phone=lead.phone,
                language=lead.language or "en",
                status="reserved",
                currency=data.currency,
                deposit_amount=data.deposit_amount,
                deposit_paid_at=_today_iso(),
                metadata_=dict(lead.metadata_ or {}),
            )
            buyer = await self.buyers.create(buyer_obj)

        reservation = await self._create_reservation_internal(
            plot=plot,
            lead_id=lead.id,
            buyer_id=buyer.id if buyer is not None else None,
            tenant_id=lead.tenant_id,
            deposit_amount=data.deposit_amount,
            currency=data.currency,
            cooling_off_days=data.cooling_off_days,
            expires_at=data.expires_at,
            metadata={"converted_from_lead": str(lead_id)},
        )

        # Mark lead converted.
        await self.leads.update_fields(
            lead_id,
            status="converted",
            converted_to_buyer_id=buyer.id if buyer is not None else None,
        )
        # Flip plot to reserved unless already past reservation gate.
        if plot.status in {"planned", "under_construction", "ready"}:
            await self.plots.update_fields(plot.id, status="reserved")

        event_bus.publish_detached(
            "property_dev.lead.converted",
            data={
                "lead_id": str(lead_id),
                "reservation_id": str(reservation.id),
                "buyer_id": str(buyer.id) if buyer is not None else None,
                "plot_id": str(plot.id),
                "deposit_amount": str(reservation.deposit_amount),
                "currency": reservation.currency,
            },
            source_module="property_dev",
        )
        return reservation

    # ── Reservation ─────────────────────────────────────────────────────

    async def _next_reservation_number(self, plot: Plot) -> str:
        """Compute the next per-development reservation number.

        Numbering format: ``RES-{development_code}-{seq:05d}`` where
        ``seq`` is the count of reservations on this plot + 1.
        """
        dev = await self.developments.get_by_id(plot.development_id)
        dev_code = (dev.code if dev else "DEV").upper()
        seq = await self.reservations.next_sequence_for_plot(plot.id)
        return f"RES-{dev_code}-{seq:05d}"

    async def _create_reservation_internal(
        self,
        *,
        plot: Plot,
        lead_id: uuid.UUID | None,
        buyer_id: uuid.UUID | None,
        tenant_id: uuid.UUID | None,
        deposit_amount: Decimal,
        currency: str,
        cooling_off_days: int,
        expires_at: str | None,
        reservation_number: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Reservation:
        if reservation_number is None:
            reservation_number = await self._next_reservation_number(plot)
        today = datetime.now(UTC).date()
        cooling_off_until = (
            today + timedelta(days=cooling_off_days)
        ).isoformat()
        obj = Reservation(
            plot_id=plot.id,
            lead_id=lead_id,
            buyer_id=buyer_id,
            tenant_id=tenant_id,
            reservation_number=reservation_number,
            deposit_amount=deposit_amount,
            currency=currency,
            deposit_paid_at=datetime.now(UTC),
            cooling_off_days=cooling_off_days,
            cooling_off_until=cooling_off_until,
            expires_at=expires_at,
            status="active",
            metadata_=metadata or {},
        )
        reservation = await self.reservations.create(obj)
        event_bus.publish_detached(
            "property_dev.reservation.created",
            data={
                "reservation_id": str(reservation.id),
                "plot_id": str(plot.id),
                "lead_id": str(lead_id) if lead_id else None,
                "buyer_id": str(buyer_id) if buyer_id else None,
                "deposit_amount": str(deposit_amount),
                "currency": currency,
            },
            source_module="property_dev",
        )
        return reservation

    async def create_reservation(self, data: ReservationCreate) -> Reservation:
        plot = await self.plots.get_by_id(data.plot_id)
        if plot is None:
            raise HTTPException(status_code=422, detail="plot not found")
        if plot.status in {"sold", "handed_over"}:
            raise HTTPException(
                status_code=409,
                detail=f"Plot {plot.plot_number} not available for reservation",
            )
        # Validate lead/buyer ids if provided.
        if data.lead_id is not None and await self.leads.get_by_id(data.lead_id) is None:
            raise HTTPException(status_code=422, detail="lead not found")
        if data.buyer_id is not None and await self.buyers.get_by_id(data.buyer_id) is None:
            raise HTTPException(status_code=422, detail="buyer not found")
        return await self._create_reservation_internal(
            plot=plot,
            lead_id=data.lead_id,
            buyer_id=data.buyer_id,
            tenant_id=data.tenant_id,
            deposit_amount=data.deposit_amount,
            currency=data.currency,
            cooling_off_days=data.cooling_off_days,
            expires_at=data.expires_at,
            reservation_number=data.reservation_number,
            metadata=data.metadata,
        )

    async def get_reservation(self, r_id: uuid.UUID) -> Reservation:
        obj = await self.reservations.get_by_id(r_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Reservation not found")
        return obj

    async def update_reservation(
        self, r_id: uuid.UUID, data: ReservationUpdate
    ) -> Reservation:
        res = await self.get_reservation(r_id)
        if res.status != "active":
            raise HTTPException(
                status_code=409,
                detail=f"Reservation in status '{res.status}' is read-only",
            )
        fields = _dump(data)
        if fields:
            await self.reservations.update_fields(r_id, **fields)
        return await self.get_reservation(r_id)

    async def cancel_reservation(self, r_id: uuid.UUID) -> Reservation:
        res = await self.get_reservation(r_id)
        _ensure_transition(
            "reservation",
            res.status,
            "cancelled",
            allowed_reservation_transitions,
        )
        await self.reservations.update_fields(r_id, status="cancelled")
        cancelled = await self.get_reservation(r_id)
        # Free plot if it was held for this reservation.
        plot = await self.plots.get_by_id(cancelled.plot_id)
        if plot is not None and plot.status == "reserved":
            await self.plots.update_fields(plot.id, status="planned")
        event_bus.publish_detached(
            "property_dev.reservation.cancelled",
            data={
                "reservation_id": str(r_id),
                "plot_id": str(cancelled.plot_id),
            },
            source_module="property_dev",
        )
        return cancelled

    async def expire_reservation(self, r_id: uuid.UUID) -> Reservation:
        res = await self.get_reservation(r_id)
        _ensure_transition(
            "reservation",
            res.status,
            "expired",
            allowed_reservation_transitions,
        )
        await self.reservations.update_fields(r_id, status="expired")
        expired = await self.get_reservation(r_id)
        # Free plot if it was held.
        plot = await self.plots.get_by_id(expired.plot_id)
        if plot is not None and plot.status == "reserved":
            await self.plots.update_fields(plot.id, status="planned")
        event_bus.publish_detached(
            "property_dev.reservation.expired",
            data={
                "reservation_id": str(r_id),
                "plot_id": str(expired.plot_id),
            },
            source_module="property_dev",
        )
        return expired

    async def expire_overdue_reservations(self) -> list[uuid.UUID]:
        """Expire every active reservation whose ``expires_at`` is past.

        Returns the list of expired reservation IDs. Safe to call from a
        cron-driven endpoint or from a daily job; idempotent.
        """
        today = datetime.now(UTC).date().isoformat()
        expired = await self.reservations.find_expired(today_iso=today)
        out: list[uuid.UUID] = []
        for res in expired:
            try:
                await self.expire_reservation(res.id)
                out.append(res.id)
            except HTTPException:
                # Transition conflict (already mutated by another path) —
                # skip, do not abort the batch.
                continue
        return out

    async def convert_reservation_to_spa(
        self,
        r_id: uuid.UUID,
        data: ReservationConvertToSpaRequest,
    ) -> SalesContract:
        res = await self.get_reservation(r_id)
        if res.status != "active":
            raise HTTPException(
                status_code=409,
                detail=f"Reservation in status '{res.status}' cannot convert",
            )
        plot = await self.plots.get_by_id(res.plot_id)
        if plot is None:
            raise HTTPException(
                status_code=409, detail="Plot for reservation has gone away"
            )

        contract_number = data.contract_number or await self._next_contract_number(
            plot
        )
        obj = SalesContract(
            contract_number=contract_number,
            plot_id=plot.id,
            reservation_id=r_id,
            tenant_id=res.tenant_id,
            signing_date=data.signing_date,
            governing_law=data.governing_law or "",
            language=data.language or "en",
            total_price_breakdown=data.total_price_breakdown,
            total_value=data.total_value,
            currency=data.currency,
            status="draft",
            terms_version=data.terms_version,
            metadata_=data.metadata,
        )
        spa = await self.sales_contracts.create(obj)

        # Mark reservation converted + buyer/plot transition.
        await self.reservations.update_fields(r_id, status="converted")
        if res.buyer_id is not None:
            buyer = await self.buyers.get_by_id(res.buyer_id)
            if buyer is not None and buyer.status == "reserved":
                await self.buyers.update_fields(
                    res.buyer_id,
                    status="contracted",
                    contract_value=data.total_value,
                    currency=data.currency,
                    contract_signed_at=data.signing_date,
                )
        if plot.status == "reserved":
            await self.plots.update_fields(plot.id, status="sold")

        # Default payment schedule (single milestone @ spa_signed).
        await self._create_default_payment_schedule(spa)

        event_bus.publish_detached(
            "property_dev.spa.created",
            data={
                "spa_id": str(spa.id),
                "plot_id": str(plot.id),
                "reservation_id": str(r_id),
                "total_value": str(spa.total_value),
                "currency": spa.currency,
            },
            source_module="property_dev",
        )
        return spa

    # ── SalesContract ──────────────────────────────────────────────────

    async def _next_contract_number(self, plot: Plot) -> str:
        dev = await self.developments.get_by_id(plot.development_id)
        dev_code = (dev.code if dev else "DEV").upper()
        seq = await self.sales_contracts.next_sequence_for_plot(plot.id)
        return f"SPA-{dev_code}-{seq:05d}"

    async def _create_default_payment_schedule(
        self, spa: SalesContract
    ) -> PaymentSchedule:
        """Create a single-line ``spa_signed`` schedule by default."""
        schedule_obj = PaymentSchedule(
            sales_contract_id=spa.id,
            tenant_id=spa.tenant_id,
            currency=spa.currency,
            total_amount=spa.total_value,
            status="active",
            metadata_={"auto_created": True},
        )
        schedule = await self.payment_schedules.create(schedule_obj)
        await self.instalments.create(
            Instalment(
                schedule_id=schedule.id,
                sequence=1,
                milestone_label="Full balance @ SPA signature",
                milestone_event="spa_signed",
                due_date=spa.signing_date,
                amount=spa.total_value,
                status="pending",
            )
        )
        return schedule

    async def create_spa(self, data: SalesContractCreate) -> SalesContract:
        plot = await self.plots.get_by_id(data.plot_id)
        if plot is None:
            raise HTTPException(status_code=422, detail="plot not found")
        contract_number = data.contract_number or await self._next_contract_number(
            plot
        )
        obj = SalesContract(
            contract_number=contract_number,
            plot_id=plot.id,
            reservation_id=data.reservation_id,
            tenant_id=data.tenant_id,
            signing_date=data.signing_date,
            governing_law=data.governing_law or "",
            language=data.language or "en",
            total_price_breakdown=data.total_price_breakdown,
            total_value=data.total_value,
            currency=data.currency or "",
            e_sign_envelope_id=data.e_sign_envelope_id,
            status="draft",
            parent_contract_id=data.parent_contract_id,
            revision_number=data.revision_number,
            terms_version=data.terms_version,
            metadata_=data.metadata,
        )
        spa = await self.sales_contracts.create(obj)
        event_bus.publish_detached(
            "property_dev.spa.draft_created",
            data={
                "spa_id": str(spa.id),
                "plot_id": str(plot.id),
                "total_value": str(spa.total_value),
                "currency": spa.currency,
            },
            source_module="property_dev",
        )
        return spa

    async def get_spa(self, spa_id: uuid.UUID) -> SalesContract:
        obj = await self.sales_contracts.get_by_id(spa_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="SalesContract not found")
        return obj

    async def update_spa(
        self, spa_id: uuid.UUID, data: SalesContractUpdate
    ) -> SalesContract:
        spa = await self.get_spa(spa_id)
        if spa.status not in {"draft", "sent_for_signature"}:
            raise HTTPException(
                status_code=409,
                detail=f"SalesContract in status '{spa.status}' is read-only",
            )
        fields = _dump(data)
        if fields:
            await self.sales_contracts.update_fields(spa_id, **fields)
        return await self.get_spa(spa_id)

    async def delete_spa(self, spa_id: uuid.UUID) -> None:
        spa = await self.get_spa(spa_id)
        if spa.status != "draft":
            raise HTTPException(
                status_code=409,
                detail="Only draft SalesContracts can be deleted",
            )
        await self.sales_contracts.delete(spa_id)

    async def send_spa_for_signature(
        self,
        spa_id: uuid.UUID,
        data: SalesContractSendForSignatureRequest,
    ) -> SalesContract:
        spa = await self.get_spa(spa_id)
        _ensure_transition(
            "spa",
            spa.status,
            "sent_for_signature",
            allowed_spa_transitions,
        )
        # Require at least one party with role=primary.
        parties = await self.contract_parties.list_for_contract(spa_id)
        if not any(p.party_role == "primary" for p in parties):
            raise HTTPException(
                status_code=409,
                detail="SalesContract has no primary party — cannot send",
            )
        fields: dict[str, Any] = {"status": "sent_for_signature"}
        if data.e_sign_envelope_id is not None:
            fields["e_sign_envelope_id"] = data.e_sign_envelope_id
        await self.sales_contracts.update_fields(spa_id, **fields)
        sent = await self.get_spa(spa_id)
        event_bus.publish_detached(
            "property_dev.spa.sent_for_signature",
            data={
                "spa_id": str(spa_id),
                "envelope_id": sent.e_sign_envelope_id,
                "party_count": len(parties),
            },
            source_module="property_dev",
        )
        return sent

    async def sign_spa(
        self, spa_id: uuid.UUID, data: SalesContractSignRequest
    ) -> SalesContract:
        """Counter-sign the SPA on the developer side."""
        spa = await self.get_spa(spa_id)
        # Allow counter-sign from signed → countersigned (typical path)
        # or from sent_for_signature when buyer + developer co-sign at once.
        if spa.status == "signed":
            target = "countersigned"
        elif spa.status in {"sent_for_signature", "partially_signed"}:
            target = "signed"
        else:
            raise HTTPException(
                status_code=409,
                detail=f"SalesContract in status '{spa.status}' cannot be signed",
            )
        _ensure_transition("spa", spa.status, target, allowed_spa_transitions)
        fields: dict[str, Any] = {"status": target}
        if data.signing_date and not spa.signing_date:
            fields["signing_date"] = data.signing_date
        await self.sales_contracts.update_fields(spa_id, **fields)
        signed = await self.get_spa(spa_id)

        # Auto-activate the linked payment schedule on countersign.
        if target == "countersigned":
            schedule = await self.payment_schedules.get_for_contract(spa_id)
            if schedule is not None and schedule.status == "active":
                # Schedule already active → fire spa_signed milestone.
                await self._fire_milestone(spa_id, "spa_signed")

        event_bus.publish_detached(
            "property_dev.spa.signed",
            data={
                "spa_id": str(spa_id),
                "plot_id": str(signed.plot_id),
                "status": signed.status,
                "signing_date": signed.signing_date,
            },
            source_module="property_dev",
        )
        return signed

    async def cancel_spa(self, spa_id: uuid.UUID) -> SalesContract:
        spa = await self.get_spa(spa_id)
        _ensure_transition(
            "spa", spa.status, "cancelled", allowed_spa_transitions
        )
        await self.sales_contracts.update_fields(spa_id, status="cancelled")
        # Suspend the schedule.
        schedule = await self.payment_schedules.get_for_contract(spa_id)
        if schedule is not None and schedule.status == "active":
            await self.payment_schedules.update_fields(
                schedule.id, status="cancelled"
            )
        event_bus.publish_detached(
            "property_dev.spa.cancelled",
            data={"spa_id": str(spa_id)},
            source_module="property_dev",
        )
        return await self.get_spa(spa_id)

    # ── PaymentSchedule ────────────────────────────────────────────────

    async def create_payment_schedule(
        self, data: PaymentScheduleCreate
    ) -> PaymentSchedule:
        spa = await self.get_spa(data.sales_contract_id)
        existing = await self.payment_schedules.get_for_contract(spa.id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="PaymentSchedule already exists for this SPA",
            )
        obj = PaymentSchedule(
            sales_contract_id=spa.id,
            tenant_id=data.tenant_id,
            currency=data.currency,
            total_amount=data.total_amount,
            late_fee_pct=data.late_fee_pct,
            grace_period_days=data.grace_period_days,
            status="active",
            metadata_=data.metadata,
        )
        return await self.payment_schedules.create(obj)

    async def get_payment_schedule(
        self, schedule_id: uuid.UUID
    ) -> PaymentSchedule:
        obj = await self.payment_schedules.get_by_id(schedule_id)
        if obj is None:
            raise HTTPException(
                status_code=404, detail="PaymentSchedule not found"
            )
        return obj

    async def update_payment_schedule(
        self, schedule_id: uuid.UUID, data: PaymentScheduleUpdate
    ) -> PaymentSchedule:
        await self.get_payment_schedule(schedule_id)
        fields = _dump(data)
        if fields:
            await self.payment_schedules.update_fields(schedule_id, **fields)
        return await self.get_payment_schedule(schedule_id)

    async def activate_payment_schedule(
        self, schedule_id: uuid.UUID
    ) -> PaymentSchedule:
        """Activate a suspended schedule and mark the first pending line due."""
        schedule = await self.get_payment_schedule(schedule_id)
        if schedule.status == "active":
            # Idempotent — but still mark first pending instalment due.
            await self._mark_first_pending_due(schedule_id)
            return schedule
        _ensure_transition(
            "payment_schedule",
            schedule.status,
            "active",
            allowed_payment_schedule_transitions,
        )
        await self.payment_schedules.update_fields(schedule_id, status="active")
        await self._mark_first_pending_due(schedule_id)
        activated = await self.get_payment_schedule(schedule_id)
        event_bus.publish_detached(
            "property_dev.payment_schedule.activated",
            data={
                "schedule_id": str(schedule_id),
                "sales_contract_id": str(activated.sales_contract_id),
            },
            source_module="property_dev",
        )
        return activated

    async def suspend_payment_schedule(
        self, schedule_id: uuid.UUID
    ) -> PaymentSchedule:
        schedule = await self.get_payment_schedule(schedule_id)
        _ensure_transition(
            "payment_schedule",
            schedule.status,
            "suspended",
            allowed_payment_schedule_transitions,
        )
        await self.payment_schedules.update_fields(
            schedule_id, status="suspended"
        )
        return await self.get_payment_schedule(schedule_id)

    async def _mark_first_pending_due(self, schedule_id: uuid.UUID) -> None:
        instalments = await self.instalments.list_for_schedule(schedule_id)
        for ins in instalments:
            if ins.status == "pending":
                await self.instalments.update_fields(ins.id, status="due")
                break

    # ── Instalment ─────────────────────────────────────────────────────

    async def create_instalment(self, data: InstalmentCreate) -> Instalment:
        schedule = await self.get_payment_schedule(data.schedule_id)
        if schedule.status not in {"active", "suspended"}:
            raise HTTPException(
                status_code=409,
                detail=f"Schedule in status '{schedule.status}' is read-only",
            )
        obj = Instalment(
            schedule_id=schedule.id,
            sequence=data.sequence,
            milestone_label=data.milestone_label,
            milestone_event=data.milestone_event,
            due_date=data.due_date,
            amount=data.amount,
            status="pending",
            invoice_ref=data.invoice_ref,
            metadata_=data.metadata,
        )
        return await self.instalments.create(obj)

    async def get_instalment(self, ins_id: uuid.UUID) -> Instalment:
        obj = await self.instalments.get_by_id(ins_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Instalment not found")
        return obj

    async def update_instalment(
        self, ins_id: uuid.UUID, data: InstalmentUpdate
    ) -> Instalment:
        ins = await self.get_instalment(ins_id)
        if ins.status in {"paid", "waived", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Instalment in status '{ins.status}' is read-only",
            )
        fields = _dump(data)
        if fields:
            await self.instalments.update_fields(ins_id, **fields)
        return await self.get_instalment(ins_id)

    async def mark_instalment_paid(
        self,
        ins_id: uuid.UUID,
        data: InstalmentMarkPaidRequest,
    ) -> Instalment:
        ins = await self.get_instalment(ins_id)
        if ins.status in {"paid", "waived", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Instalment in status '{ins.status}' is read-only",
            )
        amount = Decimal(str(data.amount))
        if amount <= 0:
            raise HTTPException(
                status_code=422, detail="amount must be > 0"
            )
        current_paid = Decimal(str(ins.amount_paid or 0))
        new_paid = current_paid + amount
        owed = Decimal(str(ins.amount or 0))
        # Allow over-pay tolerance of 0.01 (rounding); else 422.
        if new_paid > owed + Decimal("0.01"):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"payment {amount} exceeds outstanding "
                    f"{owed - current_paid}"
                ),
            )
        new_status = "paid" if new_paid >= owed - Decimal("0.01") else ins.status
        if new_status == "paid":
            _ensure_transition(
                "instalment",
                ins.status,
                "paid",
                allowed_instalment_transitions,
            )
        fields: dict[str, Any] = {
            "amount_paid": new_paid.quantize(Decimal("0.01")),
        }
        if new_status == "paid":
            fields["status"] = "paid"
            fields["paid_at"] = (
                data.paid_at or datetime.now(UTC)
            )
        if data.invoice_ref:
            fields["invoice_ref"] = data.invoice_ref
        await self.instalments.update_fields(ins_id, **fields)
        updated = await self.get_instalment(ins_id)

        # Schedule completion check.
        if new_status == "paid":
            await self._maybe_complete_schedule(updated.schedule_id)

        event_bus.publish_detached(
            "property_dev.instalment.paid",
            data={
                "instalment_id": str(ins_id),
                "schedule_id": str(updated.schedule_id),
                "amount_paid": str(amount),
                "amount_total_paid": str(new_paid),
                "status": updated.status,
            },
            source_module="property_dev",
        )
        # Cashflow signal for finance.
        event_bus.publish_detached(
            "finance.cashflow.actual_received",
            data={
                "source_module": "property_dev",
                "source_id": str(ins_id),
                "schedule_id": str(updated.schedule_id),
                "amount": str(amount),
            },
            source_module="property_dev",
        )
        return updated

    async def issue_instalment_demand(
        self, ins_id: uuid.UUID
    ) -> Instalment:
        """Emit a demand-letter event for the correspondence module.

        The correspondence module subscribes to
        ``correspondence.outbound.requested`` and is responsible for
        templating, signing and sending. This method only stages the
        intent + records it on the instalment metadata.
        """
        ins = await self.get_instalment(ins_id)
        if ins.status in {"paid", "waived", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Instalment in status '{ins.status}' — no demand",
            )
        # Mark overdue if past due_date.
        today = datetime.now(UTC).date().isoformat()
        if (
            ins.due_date
            and ins.due_date < today
            and ins.status in {"pending", "due"}
        ):
            _ensure_transition(
                "instalment",
                ins.status,
                "overdue",
                allowed_instalment_transitions,
            )
            await self.instalments.update_fields(ins_id, status="overdue")

        event_bus.publish_detached(
            "correspondence.outbound.requested",
            data={
                "template": "INSTALMENT_DEMAND",
                "instalment_id": str(ins_id),
                "schedule_id": str(ins.schedule_id),
                "amount_outstanding": str(
                    (Decimal(str(ins.amount or 0))
                     - Decimal(str(ins.amount_paid or 0)))
                ),
                "due_date": ins.due_date,
                "milestone_label": ins.milestone_label,
            },
            source_module="property_dev",
        )
        return await self.get_instalment(ins_id)

    async def waive_instalment(
        self, ins_id: uuid.UUID, data: InstalmentWaiveRequest
    ) -> Instalment:
        ins = await self.get_instalment(ins_id)
        _ensure_transition(
            "instalment",
            ins.status,
            "waived",
            allowed_instalment_transitions,
        )
        md = dict(ins.metadata_ or {})
        md["waiver_reason"] = data.reason
        md["waived_at"] = datetime.now(UTC).isoformat()
        await self.instalments.update_fields(
            ins_id, status="waived", metadata_=md
        )
        await self._maybe_complete_schedule(ins.schedule_id)
        event_bus.publish_detached(
            "property_dev.instalment.waived",
            data={
                "instalment_id": str(ins_id),
                "schedule_id": str(ins.schedule_id),
                "reason": data.reason,
            },
            source_module="property_dev",
        )
        return await self.get_instalment(ins_id)

    async def accrue_late_fees_daily(self) -> dict[str, Any]:
        """Accrue one day of late fees on every overdue instalment.

        Late fee delta = ``schedule.late_fee_pct / 100 * outstanding``.
        Pure no-op when no schedules have a non-zero fee.
        """
        today = datetime.now(UTC).date().isoformat()
        overdue = await self.instalments.list_overdue(today_iso=today)
        touched = 0
        total_accrued = Decimal("0")
        for ins in overdue:
            schedule = await self.payment_schedules.get_by_id(ins.schedule_id)
            if schedule is None or schedule.status != "active":
                continue
            pct = Decimal(str(schedule.late_fee_pct or 0))
            if pct <= 0:
                continue
            grace = schedule.grace_period_days or 0
            try:
                due = date.fromisoformat(ins.due_date)
            except (TypeError, ValueError):
                continue
            today_d = date.fromisoformat(today)
            if (today_d - due).days <= grace:
                continue
            outstanding = (
                Decimal(str(ins.amount or 0))
                - Decimal(str(ins.amount_paid or 0))
            )
            if outstanding <= 0:
                continue
            delta = (outstanding * pct / Decimal("100") / Decimal("365"))
            delta = delta.quantize(Decimal("0.01"))
            if delta <= 0:
                continue
            new_accrued = (
                Decimal(str(ins.late_fee_accrued or 0)) + delta
            ).quantize(Decimal("0.01"))
            # Move pending → overdue if not already.
            new_status = "overdue" if ins.status != "overdue" else ins.status
            await self.instalments.update_fields(
                ins.id,
                late_fee_accrued=new_accrued,
                status=new_status,
            )
            touched += 1
            total_accrued += delta
        return {
            "touched_count": touched,
            "total_accrued": total_accrued,
        }

    async def _maybe_complete_schedule(self, schedule_id: uuid.UUID) -> None:
        """If all instalments are paid/waived → mark schedule completed."""
        items = await self.instalments.list_for_schedule(schedule_id)
        if not items:
            return
        if all(i.status in {"paid", "waived", "cancelled"} for i in items):
            await self.payment_schedules.update_fields(
                schedule_id, status="completed"
            )
            event_bus.publish_detached(
                "property_dev.payment_schedule.completed",
                data={"schedule_id": str(schedule_id)},
                source_module="property_dev",
            )

    async def _fire_milestone(
        self, spa_id: uuid.UUID, milestone_event: str
    ) -> int:
        """Mark every pending instalment matching ``milestone_event`` as due.

        Returns the number of instalments touched.
        """
        # All instalments on this SPA whose milestone matches.
        ins_rows = await self.instalments.list_for_contract(spa_id)
        touched = 0
        for ins in ins_rows:
            if (
                ins.milestone_event == milestone_event
                and ins.status == "pending"
            ):
                await self.instalments.update_fields(ins.id, status="due")
                touched += 1
        return touched

    # ── ContractParty ──────────────────────────────────────────────────

    async def add_contract_party(
        self, data: ContractPartyCreate
    ) -> ContractParty:
        spa = await self.get_spa(data.sales_contract_id)
        if spa.status not in {"draft", "sent_for_signature"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"SalesContract in status '{spa.status}' is "
                    "locked — no party changes"
                ),
            )
        buyer = await self.buyers.get_by_id(data.buyer_id)
        if buyer is None:
            raise HTTPException(status_code=422, detail="buyer not found")
        existing = await self.contract_parties.find_existing(
            spa.id, data.buyer_id
        )
        if existing is not None:
            raise HTTPException(
                status_code=409, detail="Buyer is already a party"
            )
        # Validate sum of ownership_pct including the new row.
        parties = await self.contract_parties.list_for_contract(spa.id)
        current_total = sum(
            (Decimal(str(p.ownership_pct or 0)) for p in parties),
            Decimal("0"),
        )
        new_total = current_total + Decimal(str(data.ownership_pct))
        if new_total > Decimal("100"):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"ownership_pct sum would be {new_total} > 100"
                ),
            )
        obj = ContractParty(
            sales_contract_id=spa.id,
            buyer_id=data.buyer_id,
            ownership_pct=data.ownership_pct,
            party_role=data.party_role,
            signing_order=data.signing_order,
            signature_ref=data.signature_ref,
            metadata_=data.metadata,
        )
        party = await self.contract_parties.create(obj)
        event_bus.publish_detached(
            "property_dev.contract_party.added",
            data={
                "spa_id": str(spa.id),
                "buyer_id": str(data.buyer_id),
                "party_id": str(party.id),
                "ownership_pct": str(party.ownership_pct),
                "party_role": party.party_role,
                "ownership_total": str(new_total),
            },
            source_module="property_dev",
        )
        return party

    async def get_contract_party(self, party_id: uuid.UUID) -> ContractParty:
        obj = await self.contract_parties.get_by_id(party_id)
        if obj is None:
            raise HTTPException(
                status_code=404, detail="ContractParty not found"
            )
        return obj

    async def update_contract_party(
        self, party_id: uuid.UUID, data: ContractPartyUpdate
    ) -> ContractParty:
        party = await self.get_contract_party(party_id)
        fields = _dump(data)
        # Validate ownership-sum if pct is changing.
        if "ownership_pct" in fields and fields["ownership_pct"] is not None:
            spa = await self.get_spa(party.sales_contract_id)
            if spa.status not in {"draft", "sent_for_signature"}:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"SPA in status '{spa.status}' — ownership "
                        "is locked"
                    ),
                )
            parties = await self.contract_parties.list_for_contract(
                party.sales_contract_id
            )
            new_total = Decimal("0")
            for p in parties:
                if p.id == party_id:
                    new_total += Decimal(str(fields["ownership_pct"]))
                else:
                    new_total += Decimal(str(p.ownership_pct or 0))
            if new_total > Decimal("100"):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"ownership_pct sum would be {new_total} > 100"
                    ),
                )
        await self.contract_parties.update_fields(party_id, **fields)
        return await self.get_contract_party(party_id)

    async def remove_contract_party(self, party_id: uuid.UUID) -> None:
        party = await self.get_contract_party(party_id)
        spa = await self.get_spa(party.sales_contract_id)
        if spa.status not in {"draft", "sent_for_signature"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"SPA in status '{spa.status}' — parties are "
                    "locked"
                ),
            )
        await self.contract_parties.delete(party_id)
        event_bus.publish_detached(
            "property_dev.contract_party.removed",
            data={
                "spa_id": str(party.sales_contract_id),
                "buyer_id": str(party.buyer_id),
                "party_id": str(party_id),
            },
            source_module="property_dev",
        )


# ── Helpers ─────────────────────────────────────────────────────────────


def _dump(data: Any) -> dict[str, Any]:
    """Pydantic v2 ``model_dump`` that maps ``metadata`` → ``metadata_``."""
    fields = data.model_dump(exclude_unset=True)
    if "metadata" in fields:
        fields["metadata_"] = fields.pop("metadata")
    return fields


__all__ = [
    "PropertyDevService",
    "allowed_buyer_transitions",
    "allowed_handover_transitions",
    "allowed_instalment_transitions",
    "allowed_lead_transitions",
    "allowed_payment_schedule_transitions",
    "allowed_plot_transitions",
    "allowed_reservation_transitions",
    "allowed_selection_transitions",
    "allowed_spa_transitions",
    "allowed_warranty_transitions",
    "can_modify_selection",
    "compute_buyer_selection_total",
    "compute_deposit_forfeiture",
    "compute_freeze_deadline",
    "compute_plot_final_price",
    "derive_plot_construction_progress",
    "supported_jurisdictions",
    "validate_option_compatibility",
]
