# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍Pydantic schemas for the clash cost-impact module.

All money values are serialised as ``float`` on the wire because the
frontend's ``MoneyDisplay`` reads ``number``; the service layer keeps
arithmetic in ``Decimal`` internally and only narrows to ``float`` at
the response boundary (matching the BOQ module's wire convention).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class AffectedPosition(BaseModel):
    """A BOQ position that participates in a clash's rework subtotal.

    The list lets a quantity surveyor click through to the exact lines
    that the rework factor was applied to — defensible numbers, not a
    black-box guess.
    """

    model_config = ConfigDict(from_attributes=True)

    position_id: uuid.UUID
    ordinal: str = ""
    description: str = ""
    total: float = 0.0


class CostImpactComponents(BaseModel):
    """Breakdown of the cost impact for tooltip surfacing in the UI."""

    rework_positions_total: float = Field(
        default=0.0,
        description="Sum of the affected BOQ positions' ``total`` "
        "(quantity × unit_rate) BEFORE the rework factor.",
    )
    rework_factor_pct: float = Field(
        default=10.0,
        description="Project-configurable rework factor as a percentage "
        "(default 10%). Multiplied by ``rework_positions_total`` to "
        "obtain ``rework_subtotal``.",
    )
    rework_subtotal: float = Field(
        default=0.0,
        description="``rework_positions_total × (rework_factor_pct / 100)``.",
    )
    labour_hours: float = Field(
        default=0.0,
        description="Labour hours pulled from the trade-pair lookup for "
        "the clashing disciplines (symmetric on the pair).",
    )
    blended_rate: float = Field(
        default=0.0,
        description="Project-level blended labour rate per hour in the "
        "project's native currency (default 50.0).",
    )
    labour_subtotal: float = Field(
        default=0.0,
        description="``labour_hours × blended_rate``.",
    )


class ClashCostImpactResponse(BaseModel):
    """Cost impact for a single clash.

    ``confidence`` is the surveyor-honest label for how reliable the
    figure is:

    * ``high``   — at least one BOQ position links to one of the clash's
      element GUIDs. ``rework_subtotal`` carries real money.
    * ``medium`` — no BOQ overlap; the figure is the trade-pair labour
      estimate only. The UI should treat it as an order-of-magnitude
      hint, not an invoice.
    * ``low``    — neither side has data (no element GUIDs OR no labour
      lookup hit). The total is zero / token; do not present it as a
      number the QS can defend.
    """

    clash_id: uuid.UUID
    currency: str = ""
    components: CostImpactComponents
    total_estimate: float = 0.0
    confidence: str = "low"
    affected_positions: list[AffectedPosition] = Field(default_factory=list)


class TradePairImpact(BaseModel):
    """One discipline-pair cell of the project-level rollup."""

    pair: list[str] = Field(default_factory=list, max_length=2)
    count: int = 0
    total: float = 0.0


class ProjectCostImpactRollupResponse(BaseModel):
    """Project-level cost-impact rollup over the open clashes.

    ``total_open_impact`` is the sum of every selected clash's
    ``total_estimate`` (already in the project currency, no FX
    conversion). ``by_trade_pair`` is the discipline×discipline
    breakdown — pairs are normalised to ``[min, max]`` alphabetic so
    ``(arch, struct)`` and ``(struct, arch)`` collapse into one row.
    """

    project_id: uuid.UUID
    currency: str = ""
    total_open_impact: float = 0.0
    clash_count: int = 0
    by_trade_pair: list[TradePairImpact] = Field(default_factory=list)
