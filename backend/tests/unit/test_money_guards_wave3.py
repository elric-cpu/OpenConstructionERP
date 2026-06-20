# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Money-input hardening across audit wave-3 modules (risk / qms / punchlist /
rfq_bidding).

Each module accepts a monetary value that previously had no upper-magnitude
guard. A non-finite (NaN/Infinity) or absurd-but-finite magnitude (e.g.
``1e400`` / ``1e1000``) must be rejected at the schema boundary with a clean
422 instead of being stored and later:

* poisoning a project-wide rollup (risk open-exposure, QMS COPQ), or
* raising ``InvalidOperation`` inside ``quantize()`` -> an opaque 500
  (punchlist ``rework_cost``).

These are pure Pydantic-schema tests - no database needed. They mirror
``test_changeorders_money_guard.py`` (the established precedent: _MONEY_MAX =
Decimal("1e15") + an is_finite() guard).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.punchlist.schemas import PunchItemCreate, PunchItemUpdate
from app.modules.qms.schemas import NCRCreate, NCRUpdate
from app.modules.rfq_bidding.schemas import _validate_money_amount
from app.modules.risk.schemas import RiskCreate, RiskUpdate

_PID = uuid.uuid4()

# NaN/Infinity are rejected by Pydantic for a Decimal field already; the new
# guard adds the magnitude bound (>= 1e15) that ge=0 lets through.
_ABSURD = ["NaN", "Infinity", "1e1000", "1e400", "1e15"]


# ── risk: impact_cost / response_cost (Decimal fields) ──────────────────
@pytest.mark.parametrize("bad", _ABSURD)
def test_risk_create_rejects_absurd_impact_cost(bad: str) -> None:
    with pytest.raises(ValidationError):
        RiskCreate(project_id=_PID, title="x", impact_cost=bad)


@pytest.mark.parametrize("bad", ["1e1000", "1e400", "1e15"])
def test_risk_create_rejects_absurd_response_cost(bad: str) -> None:
    with pytest.raises(ValidationError):
        RiskCreate(project_id=_PID, title="x", response_cost=bad)


@pytest.mark.parametrize("bad", _ABSURD)
def test_risk_update_rejects_absurd_impact_cost(bad: str) -> None:
    with pytest.raises(ValidationError):
        RiskUpdate(impact_cost=bad)


@pytest.mark.parametrize("ok", ["0", "1250.50", "999999999999.99"])
def test_risk_create_accepts_valid_money(ok: str) -> None:
    r = RiskCreate(project_id=_PID, title="x", impact_cost=ok, response_cost=ok)
    assert r.impact_cost == Decimal(ok)
    assert r.response_cost == Decimal(ok)


# ── qms: NCR cost_impact_amount (Decimal field -> COPQ rollup) ───────────
@pytest.mark.parametrize("bad", ["1e1000", "1e400", "1e15"])
def test_qms_ncr_create_rejects_absurd_cost(bad: str) -> None:
    with pytest.raises(ValidationError):
        NCRCreate(project_id=_PID, title="x", description="y", cost_impact_amount=bad)


def test_qms_ncr_update_rejects_absurd_cost() -> None:
    with pytest.raises(ValidationError):
        NCRUpdate(cost_impact_amount="1e400")


def test_qms_ncr_create_accepts_valid_cost() -> None:
    n = NCRCreate(project_id=_PID, title="x", description="y", cost_impact_amount="12000.50")
    assert n.cost_impact_amount == Decimal("12000.50")


# ── punchlist: rework_cost (string field -> quantize, was a 500) ─────────
@pytest.mark.parametrize("bad", ["Infinity", "1e400", "1e1000", "1e15"])
def test_punchlist_create_rejects_absurd_rework_cost(bad: str) -> None:
    # Previously "Infinity"/"1e400" passed the >= 0 check then raised
    # InvalidOperation inside quantize() -> an opaque 500. Now a clean 422.
    with pytest.raises(ValidationError):
        PunchItemCreate(project_id=_PID, title="x", rework_cost=bad)


@pytest.mark.parametrize("bad", ["Infinity", "1e400", "1e15"])
def test_punchlist_update_rejects_absurd_rework_cost(bad: str) -> None:
    with pytest.raises(ValidationError):
        PunchItemUpdate(rework_cost=bad)


def test_punchlist_create_accepts_valid_rework_cost() -> None:
    p = PunchItemCreate(project_id=_PID, title="x", rework_cost="1250.50")
    assert p.rework_cost == "1250.5"  # normalised (trailing zero dropped)


# ── rfq_bidding: bid_amount (string money validator) ────────────────────
@pytest.mark.parametrize("bad", ["1e500", "1e1000", "1e15", "Infinity", "NaN"])
def test_rfq_money_amount_rejects_absurd(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_money_amount(bad, "bid_amount")


@pytest.mark.parametrize("ok", ["0", "12000.50", "999999999999.99"])
def test_rfq_money_amount_accepts_valid(ok: str) -> None:
    # Canonical form is returned (format(d, "f")); value is preserved.
    assert Decimal(_validate_money_amount(ok, "bid_amount")) == Decimal(ok)
