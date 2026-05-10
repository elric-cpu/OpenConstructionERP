# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Build a structured CWICR Qdrant query from an :class:`ElementEnvelope`.

The legacy ranker concatenates everything (description + unit + DIN 276
+ region) into a single string and embeds it as one passage. BGE-M3 is
expressive enough that this dilutes the strong signals — the encoder
spreads its capacity across the noisy bits. The new pipeline splits
the request into three explicit channels:

* **CORE query** — short, high-signal text (category + type + material
  + distinctive specs). Drives both the ``dense`` and ``sparse``
  prefetches in :func:`app.modules.costs.qdrant_adapter.search`.
* **FILTERS** — native Qdrant predicates on the minimal payload
  (``is_abstract``, ``department_code``, ``unit_dim``). Replaces the
  Python post-filter from the LanceDB era.
* **RESOURCES query** — optional, only when the upstream extractor
  attached resource hints (concrete grade, rebar grade, etc). Drives
  the ``resources`` named-vector prefetch.

Public API:

    build_query(envelope) -> QueryPayload

The payload is a plain dataclass so the caller can pattern-match it or
splat into ``qdrant_adapter.search(**payload.search_kwargs)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.match_service.envelope import ElementEnvelope

# ── Unit → unit_dim filter value ─────────────────────────────────────────
#
# CWICR rates are unit-aware: a wall (m³) should never compete with
# flooring (m²) or pipework (m) for top-K slots. The ranker passes the
# envelope's preferred unit; we collapse it onto a coarse dimension
# class that matches the Qdrant payload's ``unit_dim`` column.
#
# When the envelope has no explicit ``unit_hint`` we infer from
# whichever quantity is present — same logic the legacy
# ``_pick_unit`` used, kept here so the query builder is
# self-contained.

_UNIT_DIM: dict[str, str] = {
    # Volume
    "m3": "volume",
    "m³": "volume",
    "cbm": "volume",
    "cum": "volume",
    # Area
    "m2": "area",
    "m²": "area",
    "sqm": "area",
    "sm": "area",
    # Length
    "m":  "length",
    "lm": "length",
    "rm": "length",
    "lfm": "length",
    # Mass
    "kg": "mass",
    "t":  "mass",
    "to": "mass",
    "ton": "mass",
    # Count
    "pcs":  "count",
    "ea":   "count",
    "stk":  "count",
    "stck": "count",
    "nr":   "count",
    "no":   "count",
    "u":    "count",
    # Time
    "h":  "time",
    "hr": "time",
    "d":  "time",
    # Lump sum — never filter, drop instead
    "ls":   "",
    "psch": "",
    "lsum": "",
}


def unit_dim_for(unit_hint: str | None) -> str | None:
    """Coarse dimension class for a CWICR unit, or ``None`` to skip filter.

    Returns ``None`` when the unit is unknown or a lump-sum — the caller
    should drop the ``unit_dim`` predicate so the search doesn't
    needlessly narrow.
    """
    if not unit_hint:
        return None
    key = unit_hint.strip().lower().replace(" ", "")
    dim = _UNIT_DIM.get(key)
    return dim or None


# ── DIN 276 → department_code filter value ───────────────────────────────
#
# The CWICR payload's ``department_code`` is the 2-digit DIN 276 KG
# prefix (33 = walls/façade, 32 = structure, 35 = roof, 44 = MEP, etc.).
# Three-digit ifc_labels hints (``"330"``, ``"334"``) collapse onto the
# same parent, so the filter activates per trade family rather than
# per granular cost group.

_DIN_PREFIX_RE = re.compile(r"^\s*(\d{2})\d?\s*")


def department_code_for(din276_hint: str | None) -> str | None:
    """Return the 2-digit DIN 276 prefix for a 3-digit hint.

    ``"330.10"`` → ``"33"``; ``"044"`` → ``"04"``; non-digit input → ``None``.
    """
    if not din276_hint:
        return None
    m = _DIN_PREFIX_RE.match(din276_hint)
    return m.group(1) if m else None


# ── Resource hint extraction ─────────────────────────────────────────────
#
# Concrete grade / rebar grade / pipe nominal — when the envelope
# attributes name a specific resource the cost rate must consume, we
# hand that off to the ``resources`` named vector. The encoder has been
# trained on the rate's top-12 unique resources so a verbatim
# concrete-grade hit lifts recall without polluting the dense channel.
#
# Patterns are intentionally narrow — anything that ends up in
# ``resources_query`` should be specific enough that a CWICR rate
# either consumes that exact resource or doesn't.

_RESOURCE_PATTERNS = (
    re.compile(r"\bC\d{2,3}/\d{2,3}\b", re.IGNORECASE),    # concrete grades C30/37, C25/30
    re.compile(r"\bB\d{3,4}[A-Z]?\b"),                       # rebar grades B500B, B500A, B420
    re.compile(r"\bDN\s?\d{2,4}\b", re.IGNORECASE),          # pipe nominals DN200, DN 100
    re.compile(r"\bM\d{1,3}(?:x\d{1,3})?\b"),                # bolt sizes M16, M16x60
    re.compile(r"\b(?:HEB|IPE|HEA|UPN|HEM)\d{2,4}\b"),       # steel profiles
    re.compile(r"\bF\s?\d{2,3}\b"),                          # fire ratings F30, F90
    re.compile(r"\bS\d{3}[A-Z]?\b"),                         # steel grades S235, S355JR
    re.compile(r"\bØ\s?\d{1,4}\b"),                          # diameter Ø14, Ø 25
)


def extract_resource_hints(envelope: ElementEnvelope) -> list[str]:
    """Pull verbatim resource tokens from the envelope text.

    Looks at ``description`` and ``properties`` values. Returns a list
    of unique tokens preserving first-seen order so the caller can
    build a stable resources_query string.
    """
    hay = [envelope.description or ""]
    for v in (envelope.properties or {}).values():
        if isinstance(v, str | int | float):
            hay.append(str(v))

    seen: dict[str, None] = {}
    for blob in hay:
        for pattern in _RESOURCE_PATTERNS:
            for match in pattern.findall(blob):
                token = match.strip().upper()
                if token and token not in seen:
                    seen[token] = None
    return list(seen.keys())


# ── v3 SearchPlan ────────────────────────────────────────────────────────
#
# Per MAPPING_PROCESS.md §4.2, the v3 contract distinguishes two filter
# tiers explicitly:
#
#   • ``hard_filters`` — Qdrant ``must`` predicates. A candidate that
#     fails the predicate is dropped before scoring. Use only when the
#     source is authoritative (BIM Pset, exact rate_code from BoQ).
#
#   • ``soft_boosts``  — multiplicative score modifiers applied AFTER
#     the RRF fusion. A candidate matching all soft_boosts ranks higher,
#     but the wrong-bucket candidates still surface so the user sees
#     them when the source's classifier was wrong.
#
# The rule of thumb (§4.2.1 verbatim): "if the filter would discard the
# correct answer when the source classifier errs → soft. If the source
# is authoritative (BIM Pset) → hard."


@dataclass
class SearchPlan:
    """Structured Qdrant search plan with explicit hard/soft tiers.

    Attributes:
        dense_query: Free-form text for the BGE-M3 ``dense`` channel.
            Same string as ``sparse_query`` since BGE-M3 emits both
            representations in one forward pass.
        sparse_query: Free-form text for the ``sparse`` channel.
            Currently identical to ``dense_query``.
        hard_filters: Native Qdrant predicates — see
            :func:`app.modules.costs.qdrant_adapter._build_filter`
            for the recognised keys.
        soft_boosts: List of ``(field, value, multiplier)`` triples
            applied to ``hit.score`` after the Qdrant RRF fusion.
            ``multiplier`` is 1.0..2.0 typically; >1.0 boosts, <1.0
            penalises (rarely used).
        resources_query: Optional 3rd channel — only set when the
            extractor pulled rare tokens (concrete grades, rebar
            grades) that the ``resources`` named vector can match.
        top_k: Final result count after re-rank. Forwarded to the
            ranker for slicing.
        prefetch: Pre-fusion candidate count per channel (dense and
            sparse each pull this many before RRF combines them).
    """

    dense_query: str
    sparse_query: str
    hard_filters: dict[str, Any] = field(default_factory=dict)
    soft_boosts: list[tuple[str, Any, float]] = field(default_factory=list)
    resources_query: str | None = None
    top_k: int = 10
    prefetch: int = 50

    @property
    def search_kwargs(self) -> dict[str, Any]:
        """Splat-friendly dict for ``qdrant_adapter.search(**kwargs)``.

        Maps the v3 ``hard_filters`` onto the adapter's ``filters``
        contract (the adapter operates on the must-list directly).
        ``soft_boosts`` are NOT forwarded — they're applied by the
        ranker after the search returns.
        """
        return {
            "core_query": self.dense_query,
            "filters": dict(self.hard_filters),
            "resources_query": self.resources_query,
        }


# ── QueryPayload (v2 back-compat) ────────────────────────────────────────


@dataclass
class QueryPayload:
    """Pre-v3 output of :func:`build_query`. Kept as a back-compat type
    so legacy callers (smoke endpoint diagnostics, eval harness) keep
    working. New code should depend on :class:`SearchPlan` instead.
    """

    core_query: str
    filters: dict[str, Any] = field(default_factory=dict)
    resources_query: str | None = None

    @property
    def search_kwargs(self) -> dict[str, Any]:
        """Splat-friendly dict for ``qdrant_adapter.search(**kwargs)``.

        ``country`` is intentionally NOT included — the caller passes it
        separately so the same envelope can be searched against multiple
        regional collections (e.g. cross-language recall checks).
        """
        return {
            "core_query": self.core_query,
            "filters": dict(self.filters),
            "resources_query": self.resources_query,
        }


# ── Soft-boost weights (v3 default; tunable later in Phase 4 recal) ──────
#
# Matches the example weights in MAPPING_PROCESS.md §4.2 so the bench-
# mark numbers (recall@10 ≈ 0.97 hybrid) are reproducible. These are
# multiplicative on the RRF score: 1.5 means the matched candidate's
# score gets a 50% bump before the final sort.

_SOFT_BOOST_OST_CATEGORY = 1.5
_SOFT_BOOST_MATERIAL = 1.3
_SOFT_BOOST_NOMINAL_SIZE = 1.2


# ── Public builders ──────────────────────────────────────────────────────


def build_search_plan(
    envelope: ElementEnvelope,
    *,
    include_resources: bool = True,
    include_unit_filter: bool = True,
    include_department_filter: bool = True,
    drop_abstract: bool = True,
) -> SearchPlan:
    """Translate an :class:`ElementEnvelope` to a v3 :class:`SearchPlan`.

    The hard-vs-soft split follows MAPPING_PROCESS.md §4.2.1:

    * ``ifc_class`` / ``ifc_predefined_type`` / ``construction_stage_hint``
      / ``is_external`` / ``is_loadbearing`` / ``is_structural`` are
      hard when present — these come from BIM Psets that the file
      authored explicitly.
    * ``ost_category`` / ``material_class`` / ``nominal_size_mm`` are
      soft — Revit OST mapping and material parsing are heuristic
      enough that a wrong classification shouldn't drop the right
      answer entirely.

    The Phase-1 ``unit_dim`` / ``department_code`` / ``is_abstract``
    filters from :func:`build_query` stay hard — they're already
    derived from the safe ``unit_hint`` / ``classifier_hint`` /
    catalogue convention paths.

    Returns:
        :class:`SearchPlan` ready to splat into ``qdrant_adapter.search``
        plus a ``soft_boosts`` list the ranker applies post-search.
    """

    # ── CORE query — already curated by _envelope_from_group ─────────
    core_query = (envelope.description or envelope.category or "").strip()
    core_query = core_query[:512]

    # ── HARD filters ────────────────────────────────────────────────
    hard: dict[str, Any] = {}
    if drop_abstract:
        hard["is_abstract"] = False

    if include_department_filter:
        din = (envelope.classifier_hint or {}).get("din276")
        dept = department_code_for(din)
        if dept:
            hard["department_code"] = dept

    if include_unit_filter:
        unit = envelope.unit_hint or _infer_unit_from_quantities(envelope.quantities or {})
        unit_dim = unit_dim_for(unit)
        if unit_dim:
            hard["unit_dim"] = unit_dim

    # v3 BIM-authoritative fields. Only attach when the envelope has
    # the value — None means the upstream extractor didn't populate it
    # and we don't want to over-narrow.
    if envelope.ifc_class:
        hard["ifc_class"] = envelope.ifc_class
    if envelope.ifc_predefined_type:
        hard["ifc_predefined_type"] = envelope.ifc_predefined_type
    if envelope.construction_stage_hint:
        hard["construction_stage"] = envelope.construction_stage_hint
    # Trinary booleans — only forward when the source explicitly said
    # ``True``. ``False`` is rarely useful as a hard filter (most rates
    # don't carry a "definitely not external" flag), and ``None`` means
    # the source didn't say.
    if envelope.is_external is True:
        hard["is_external"] = True
    if envelope.is_loadbearing is True:
        hard["is_loadbearing"] = True
    if envelope.is_structural is True:
        hard["is_structural"] = True

    # ── SOFT boosts ─────────────────────────────────────────────────
    soft: list[tuple[str, Any, float]] = []
    if envelope.ost_category:
        soft.append(("ost_category", envelope.ost_category, _SOFT_BOOST_OST_CATEGORY))
    if envelope.material_class:
        soft.append(("material_class", envelope.material_class, _SOFT_BOOST_MATERIAL))
    if envelope.nominal_size_mm:
        soft.append(("nominal_size_mm", envelope.nominal_size_mm, _SOFT_BOOST_NOMINAL_SIZE))

    # ── RESOURCES query (optional) ─────────────────────────────────
    resources_query: str | None = None
    if include_resources:
        hints = extract_resource_hints(envelope)
        if hints:
            anchor = envelope.category or ""
            resources_query = (anchor + " " + ", ".join(hints)).strip()

    return SearchPlan(
        dense_query=core_query,
        sparse_query=core_query,
        hard_filters=hard,
        soft_boosts=soft,
        resources_query=resources_query,
    )


def build_query(
    envelope: ElementEnvelope,
    *,
    include_resources: bool = True,
    include_unit_filter: bool = True,
    include_department_filter: bool = True,
    drop_abstract: bool = True,
) -> QueryPayload:
    """Pre-v3 builder. Returns a :class:`QueryPayload` for back-compat.

    New code should call :func:`build_search_plan` instead, which
    returns a richer :class:`SearchPlan` with explicit
    ``hard_filters`` and ``soft_boosts``. This helper is preserved
    so the smoke endpoint and eval harness keep working without a
    forced rewrite.
    """

    plan = build_search_plan(
        envelope,
        include_resources=include_resources,
        include_unit_filter=include_unit_filter,
        include_department_filter=include_department_filter,
        drop_abstract=drop_abstract,
    )
    return QueryPayload(
        core_query=plan.dense_query,
        filters=plan.hard_filters,
        resources_query=plan.resources_query,
    )


# ── Internal helpers ─────────────────────────────────────────────────────


def _infer_unit_from_quantities(qty: dict[str, float]) -> str | None:
    """Mirror of ``service._pick_unit`` for callers that bypass it."""

    if not qty:
        return None
    # Priority order matches the legacy heuristic.
    for key, unit in (
        ("volume_m3", "m3"),
        ("area_m2", "m2"),
        ("length_m", "m"),
        ("count", "pcs"),
        ("mass_kg", "kg"),
    ):
        if qty.get(key):
            return unit
    return None


__all__ = [
    "QueryPayload",
    "SearchPlan",
    "build_query",
    "build_search_plan",
    "department_code_for",
    "extract_resource_hints",
    "unit_dim_for",
]
