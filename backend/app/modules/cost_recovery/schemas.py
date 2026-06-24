# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pydantic schemas for the cost recovery API.

Money is carried on the wire as a string (the Decimal rendered losslessly) per
the platform money-as-string convention, so the read models are built
explicitly in the router rather than validated straight off the ORM rows.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class BackChargeCreate(BaseModel):
    """Request body to record a new back-charge."""

    source_ref: str = ""
    responsible_party: str = ""
    description: str = ""
    basis: str = ""
    gross_amount: Decimal = Decimal("0")
    chargeable_pct: Decimal = Decimal("1")
    currency: str = ""
    status: str = "proposed"


class BackChargeUpdate(BaseModel):
    """Partial update of a back-charge; only the supplied fields are changed."""

    responsible_party: str | None = None
    description: str | None = None
    basis: str | None = None
    gross_amount: Decimal | None = None
    chargeable_pct: Decimal | None = None
    status: str | None = None
    recovered_amount: Decimal | None = None


class BackChargeOut(BaseModel):
    """One back-charge with its derived chargeable / outstanding amounts."""

    id: str
    project_id: str
    source_ref: str
    responsible_party: str
    description: str
    basis: str
    gross_amount: str
    chargeable_pct: str
    chargeable_amount: str
    currency: str
    status: str
    recovered_amount: str
    outstanding: str
    is_open: bool
    agreed_at: str | None
    recovered_at: str | None


class PartyRecoveryOut(BaseModel):
    """Back-charge rollup for one responsible party in one currency."""

    party: str
    currency: str
    item_count: int
    open_count: int
    gross_total: str
    chargeable_total: str
    recovered_total: str
    outstanding_total: str


class CurrencyRecoveryOut(BaseModel):
    """Back-charge rollup for one currency across all parties."""

    currency: str
    item_count: int
    chargeable_total: str
    recovered_total: str
    outstanding_total: str


class RecoveryLedgerOut(BaseModel):
    """The project's back-charge position: per-party and per-currency rollups."""

    project_id: str
    item_count: int
    open_count: int
    primary_currency: str
    primary_outstanding: str
    by_party: list[PartyRecoveryOut]
    by_currency: list[CurrencyRecoveryOut]
