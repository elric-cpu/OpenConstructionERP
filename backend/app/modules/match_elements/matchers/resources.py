# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resources catalogue matcher — fuzzy search over ``oe_catalog_resource``.

This is the "raw materials" alternative to the CWICR composite-position
matchers. When CWICR has no good composite match for a group, the user
can pick one or more entries from this matcher and assemble a custom
position by hand.

Candidates returned here carry ``source = "resources"`` so the apply-
to-BOQ step knows it's writing a single-line custom position rather
than exploding a CWICR assembly into resource sub-rows.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz, process
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.match_service.envelope import (
    ElementEnvelope,
    MatchCandidate,
    confidence_band_for,
)
from app.modules.catalog.models import CatalogResource


def _to_float(s: str) -> float:
    try:
        return float(Decimal(s))
    except (InvalidOperation, TypeError, ValueError):
        return 0.0


class ResourcesMatcher:
    name = "resources"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rank(
        self,
        *,
        envelope: ElementEnvelope,
        project_id: uuid.UUID,  # noqa: ARG002 — region scope deferred
        catalogue_id: uuid.UUID | None = None,  # noqa: ARG002
        top_k: int = 10,
    ) -> list[MatchCandidate]:
        # The catalogue is small (typically <50K rows) so a full scan is
        # acceptable; for larger tenants we'll add an FTS index in
        # Phase A.10+.
        stmt = (
            select(
                CatalogResource.id,
                CatalogResource.resource_code,
                CatalogResource.name,
                CatalogResource.resource_type,
                CatalogResource.category,
                CatalogResource.unit,
                CatalogResource.base_price,
                CatalogResource.currency,
                CatalogResource.region,
                CatalogResource.source,
            )
            .where(CatalogResource.is_active.is_(True))
        )
        # Currency-aware filter — same universality story as LexicalMatcher.
        # A USD project shouldn't see EUR resources pretending to be USD
        # rates; restrict to project currency or unstamped legacy rows.
        project_currency = (envelope.project_currency or "").strip().upper()
        if project_currency:
            stmt = stmt.where(
                or_(
                    CatalogResource.currency == project_currency,
                    CatalogResource.currency.is_(None),
                    CatalogResource.currency == "",
                )
            )
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return []

        query = (envelope.description or envelope.category or "").strip()
        if not query:
            return []

        # Match against name + category to broaden recall — "concrete"
        # in the query should hit resources whose name is "Beton C30/37"
        # via the category "Concrete & Cement".
        choices: dict[int, str] = {
            idx: f"{row.name} — {row.category}" for idx, row in enumerate(rows)
        }
        scored = process.extract(
            query, choices, scorer=fuzz.token_set_ratio, limit=top_k,
        )

        out: list[MatchCandidate] = []
        for _matched, score, idx in scored:
            row = rows[idx]
            score_norm = float(score) / 100.0
            out.append(
                MatchCandidate(
                    id=str(row.id) if row.id else None,
                    code=row.resource_code or "",
                    description=row.name or "",
                    unit=row.unit or "",
                    unit_rate=_to_float(row.base_price or "0"),
                    currency=row.currency or "",
                    score=score_norm,
                    vector_score=0.0,
                    boosts_applied={"resources_token_set": score_norm},
                    confidence_band=confidence_band_for(score_norm),
                    region_code=row.region or "",
                    source="resources",
                    classification={
                        "resource_type": row.resource_type or "",
                        "category": row.category or "",
                    },
                )
            )
        return out
