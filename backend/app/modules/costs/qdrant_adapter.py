# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""CWICR Qdrant adapter — 30-collection multilingual cost-rate search.

Replaces the legacy ``vector_adapter`` (LanceDB + e5-small + 384-dim) for
the ``/match-elements`` path. The new pipeline holds rate vectors in
30 per-language Qdrant collections (``cwicr_<lang>``), each point
carrying three named vectors:

* ``dense``     — 1024-dim BAAI/bge-m3 of the full rate description.
* ``sparse``    — BM25-like inverted vector for verbatim term hits
                  (concrete grades, pipe nominals, bolt sizes, etc).
* ``resources`` — 1024-dim bge-m3 of the rate's top-12 unique resources.

The Qdrant payload is intentionally minimal — only keys plus filter
columns (``rate_code``, ``country``, ``department_code``, ``is_abstract``,
``rate_unit``, ``mass_*``). Heavy fields (prices, labor lines, full
resource list, budget sums — 84 columns total) are read on demand from
``<region>_workitems_costs_resources_DDC_CWICR.parquet`` via
:mod:`app.modules.costs.parquet_lookup`. Keeping the vector store narrow
keeps embedded-Qdrant disk usage manageable and lets the parquet column
set evolve without re-vectorising.

Contract
--------

This module exposes two async helpers:

* :func:`search` — one-shot hybrid search that fans out
  ``dense`` + ``sparse`` (+ optional ``resources``) prefetches and fuses
  them with Reciprocal Rank Fusion natively in the Qdrant Query API.
* :func:`lookup_full_rows` — proxy onto :mod:`parquet_lookup` so the
  ranker can stay on a single ``qdrant_adapter`` import.

Heavy imports (``qdrant_client``, ``FlagEmbedding``) are deferred to the
function body. The module is safe to import even when the optional
``[semantic]`` extra is missing — only the CWICR Qdrant path degrades,
the rest of the app keeps booting.

Deployment
----------

Two modes are supported:

* **Server** (recommended for production and for DDC's pre-built
  catalogues) — ``settings.cwicr_qdrant_url`` points at a real Qdrant
  server (Docker compose ships ``qdrant/qdrant:v1.12.5`` on ports
  6333/6334). This is the **only** mode that can ingest the v3
  snapshots DDC publishes (``*_EMBEDDINGS_BGEM3_V3_DDC_CWICR.snapshot``)
  via :meth:`QdrantClient.recover_snapshot`. Verified 2026-05-09: the
  embedded path errors with ``NotImplementedError: Snapshots are not
  supported in the local Qdrant``, see v3 plan §5 risk note.
* **Embedded** (development / smoke) — ``settings.cwicr_qdrant_path``
  spawns an in-process simulation via ``QdrantClient(path=...)``.
  Suitable when the caller vectorises rates locally with BGE-M3 and
  upserts them point-by-point. **Cannot** ingest DDC snapshots.

The adapter prefers ``url`` over ``path`` when both are configured.
``settings.cwicr_qdrant_path`` defaults to ``~/.openestimator/qdrant_cwicr/``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Public types ─────────────────────────────────────────────────────────


@dataclass
class QdrantHit:
    """One result from :func:`search`.

    ``score`` is the RRF-fused score from Qdrant Query API, not a raw
    cosine similarity. Use for relative ranking only — absolute values
    are not comparable across queries.
    """

    rate_code: str
    country: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


# ── Country → collection mapping ─────────────────────────────────────────
#
# Per MAPPING_PROCESS.md v3 (§2.1, §6.1) the 30 production CWICR
# collections are named ``cwicr_{LANG}_v3`` where ``LANG`` is the
# ISO-639-1 language code of the rates inside. One collection per
# language — Mexico, Spain and Argentina catalogues all live in
# ``cwicr_es_v3`` because BGE-M3 multilingual benefits from same-language
# clustering, and per-country narrowing is done via the ``country``
# payload predicate (see :func:`country_filter_for`).
#
# Pre-v3 (LanceDB era) we used ``cwicr_<country>`` with a hand-rolled
# remap table for USA→us / GB→uk. The v3 layout makes the remap
# unnecessary — :func:`region_language.language_for` already returns
# ``"en"`` for both USA_USD and GB_LONDON, so they correctly land in
# ``cwicr_en_v3`` together.
#
# Schema version is overridable via ``settings.cwicr_collection_version``
# so the application can flip to a future ``v4`` index without a code
# change. Empty string strips the suffix entirely for legacy installs
# that vectorised before the v3 cutover.


def _collection_version_suffix() -> str:
    """Return the configured ``_<ver>`` suffix or empty for legacy installs.

    Reads ``settings.cwicr_collection_version`` lazily so test monkeypatching
    of the env var after import still takes effect. The leading underscore
    is added here to keep the f-string at the callsite readable.
    """

    version = (getattr(get_settings(), "cwicr_collection_version", "") or "").strip()
    return f"_{version}" if version else ""


def country_to_collection(country: str | None) -> str:
    """Return the Qdrant collection name for a region/country code.

    The collection key is the **language** of the rates, not the
    country. Multiple regions sharing a language (DE_BERLIN, AT_VIENNA,
    CH_ZURICH) all resolve to the same collection (``cwicr_de_v3``).
    Per-country filtering happens via the ``country`` payload field —
    see :func:`country_filter_for`.

    Accepts both bare country codes (``"DE"``) and full region ids
    (``"DE_BERLIN"``, ``"USA_USD"``, ``"MX_MEXICO"``).

    Returns ``cwicr_en_v3`` when the input is empty or unrecognised so
    a misconfigured catalogue still hits a real collection rather than
    erroring out.
    """

    from app.core.match_service.region_language import language_for

    lang = language_for(country)
    return f"cwicr_{lang}{_collection_version_suffix()}"


def country_filter_for(country: str | None) -> str | None:
    """Return the ISO-3166 head of a region id for the ``country`` payload.

    A v3 language collection (``cwicr_es_v3``) carries rates from every
    Spanish-speaking region (ES, MX, AR). When the caller picked one
    specific catalogue (``MX_MEXICO``), the head ``"MX"`` should be
    pinned as a Qdrant payload filter so the search only sees Mexican
    rates. When the caller passed nothing or just a bare two-letter
    code (``"ES"`` meaning "search the whole Spanish collection"),
    return ``None`` so all countries within the language stay
    reachable.

    Distinguishing rule: a region id (``"DE_BERLIN"``, ``"USA_USD"``)
    pins; a bare country/language code (``"DE"``, ``"ES"``, ``"USA"``)
    does not. The underscore is the explicit signal that the caller
    meant a specific catalogue, not a language-wide search.

    The mapping intentionally does NOT remap ``USA → US``: the CWICR
    payload field uses whatever DDC writes during vectorisation, and
    we don't want to second-guess it here. If a mismatch surfaces in
    production, fix it at the data-ingest layer rather than the
    application's filter helper.
    """

    if not country or not country.strip():
        return None
    raw = country.strip().upper()
    if "_" not in raw:
        # Bare code (``DE``, ``USA``, ``RU``) — language-wide intent.
        return None
    head = raw.split("_", 1)[0]
    return head or None


# ── Lazy singletons (heavy deps deferred) ────────────────────────────────


_client: Any = None  # qdrant_client.QdrantClient
_encoder: Any = None  # FlagEmbedding.BGEM3FlagModel


def _get_client() -> Any:
    """Lazy-init a QdrantClient pointed at the configured store.

    Prefers ``cwicr_qdrant_url`` when set (shared/server mode), falls
    back to embedded ``cwicr_qdrant_path``. Raises :class:`RuntimeError`
    when neither is reachable so the caller can surface a 503 to the
    user instead of a confusing AttributeError.
    """

    global _client
    if _client is not None:
        return _client

    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:  # pragma: no cover — optional [semantic] extra
        raise RuntimeError(
            "qdrant-client is not installed; install the [semantic] extra: "
            "pip install openconstructionerp[semantic]"
        ) from exc

    s = get_settings()
    url = getattr(s, "cwicr_qdrant_url", None)
    if url:
        logger.info("CWICR Qdrant: connecting to URL %s", url)
        _client = QdrantClient(url=url)
        return _client

    path = getattr(s, "cwicr_qdrant_path", "") or os.path.expanduser(
        "~/.openestimator/qdrant_cwicr"
    )
    Path(path).mkdir(parents=True, exist_ok=True)
    logger.info("CWICR Qdrant: opening embedded store at %s", path)
    _client = QdrantClient(path=path)
    return _client


def _get_encoder() -> Any:
    """Lazy-init the BGE-M3 encoder (FP32 or INT8 ONNX).

    Returns a ``BGEM3FlagModel`` whose ``.encode()`` produces both dense
    and sparse representations in one forward pass. INT8 ONNX path
    (``gpahal/bge-m3-onnx-int8``) is the VPS default — ~700 MB on disk,
    near-FP32 recall on AVX512_VNNI hardware.
    """

    global _encoder
    if _encoder is not None:
        return _encoder

    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FlagEmbedding is not installed; install the [semantic] extra: "
            "pip install openconstructionerp[semantic]"
        ) from exc

    s = get_settings()
    model = getattr(s, "cwicr_embedding_model", "BAAI/bge-m3")
    use_int8 = getattr(s, "cwicr_embedding_int8", True)
    if use_int8:
        # The INT8 ONNX checkpoint ships under a separate HF repo. The
        # FlagEmbedding loader detects ONNX via filename, so the model
        # id swap is the only change needed.
        model = "gpahal/bge-m3-onnx-int8"

    logger.info("CWICR encoder: loading %s (int8=%s)", model, use_int8)
    _encoder = BGEM3FlagModel(model, use_fp16=not use_int8)
    return _encoder


def _encode(texts: list[str], *, with_resources: bool = False) -> dict[str, Any]:
    """Run BGE-M3 once and return dense + sparse vectors per input.

    Returns ``{"dense": list[list[float]], "sparse": list[SparseVector]}``
    where ``SparseVector`` is the qdrant_client native struct so the
    Query API accepts it as-is.
    """

    encoder = _get_encoder()
    out = encoder.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    # ``out["lexical_weights"]`` is a list of dict[token_id -> weight].
    from qdrant_client.http.models import SparseVector

    sparse_vectors: list[SparseVector] = []
    for weight_map in out["lexical_weights"]:
        # Qdrant SparseVector expects parallel index/value lists.
        # Token ids are stringified ints from FlagEmbedding — cast back.
        indices = [int(k) for k in weight_map]
        values = [float(v) for v in weight_map.values()]
        sparse_vectors.append(SparseVector(indices=indices, values=values))

    return {
        "dense": [list(map(float, v)) for v in out["dense_vecs"]],
        "sparse": sparse_vectors,
    }


# ── Public API ───────────────────────────────────────────────────────────


def _build_filter(filters: dict[str, Any]) -> Any | None:
    """Translate the adapter's filter contract to a qdrant_client Filter.

    Recognises the 29 indexed payload fields documented in
    MAPPING_PROCESS.md §2.2. Each key on the input dict translates to
    a Qdrant ``must`` predicate; lists / tuples / sets become ``MatchAny``
    (OR-of-values), scalars become ``MatchValue`` (exact match).
    Booleans are coerced to ``bool()`` so a stray "true"/"1" string
    doesn't accidentally pin to a literal-string predicate.

    Recognised keys (all optional — callers pass only what they need):

    * Boolean flags (Pset-derived): ``is_abstract``, ``is_external``,
      ``is_loadbearing``, ``is_structural``, ``is_machine``,
      ``is_material``, ``is_finishing``, ``is_temporary``,
      ``is_compound``.
    * IFC / OST classification: ``ifc_class``, ``ifc_predefined_type``,
      ``ost_category``, ``applies_to_ifc_classes``.
    * CSI / DIN: ``masterformat_division``, ``csi_division_2``,
      ``department_code``, ``subsection_code``.
    * Categorisation: ``category_type``, ``collection_name``,
      ``construction_stage``, ``uniformat_group``,
      ``classification_confidence``, ``equipment_class``.
    * Physical: ``unit_type``, ``unit_dim``, ``rate_unit``,
      ``nominal_size_mm``, ``material_class``, ``installation_method``.
    * Metadata: ``country``, ``rate_code``.

    Returns ``None`` when the filter dict is empty so the caller can
    omit it from the Query API call.
    """

    if not filters:
        return None

    from qdrant_client.http.models import (
        FieldCondition,
        Filter,
        MatchAny,
        MatchValue,
    )

    must: list[FieldCondition] = []

    # Boolean flags — coerced to ``bool()`` so polluted inputs
    # ("true" / "1" / 0.0) don't sneak through as type-mismatched
    # MatchValue predicates that Qdrant would reject silently.
    _BOOL_KEYS = (
        "is_abstract",
        "is_external",
        "is_loadbearing",
        "is_structural",
        "is_machine",
        "is_material",
        "is_finishing",
        "is_temporary",
        "is_compound",
    )
    for key in _BOOL_KEYS:
        if key in filters and filters[key] is not None:
            must.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=bool(filters[key])),
                )
            )

    # Scalar / list-of-scalar fields. Order matches the v3 §2.2 listing
    # so the next maintainer can compare visually with MAPPING_PROCESS.md.
    _SCALAR_KEYS = (
        "country",
        "ifc_class",
        "ifc_predefined_type",
        "ost_category",
        "applies_to_ifc_classes",
        "masterformat_division",
        "csi_division_2",
        "category_type",
        "collection_name",
        "department_code",
        "subsection_code",
        "unit_type",
        "unit_dim",
        "rate_unit",
        "material_class",
        "installation_method",
        "construction_stage",
        "uniformat_group",
        "equipment_class",
        "classification_confidence",
        "rate_code",
        "nominal_size_mm",
    )
    for key in _SCALAR_KEYS:
        val = filters.get(key)
        if val is None:
            continue
        if isinstance(val, list | tuple | set):
            must.append(FieldCondition(key=key, match=MatchAny(any=list(val))))
        else:
            must.append(FieldCondition(key=key, match=MatchValue(value=val)))

    if not must:
        return None
    return Filter(must=must)


async def search(
    *,
    country: str,
    core_query: str,
    resources_query: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 30,
    prefetch_limit: int = 50,
) -> list[QdrantHit]:
    """Hybrid CWICR search across dense + sparse (+ optional resources).

    One Qdrant call, three prefetches, RRF fusion native to the Query
    API. Returns up to ``limit`` :class:`QdrantHit` rows ranked by the
    fused score, payload-only. Call :func:`lookup_full_rows` afterwards
    to attach the 84-column parquet data.

    ``country`` is the region or country code passed to
    :func:`country_to_collection`. ``filters`` follows the contract in
    :func:`_build_filter`.
    """

    collection = country_to_collection(country)
    # v3: a single language collection holds rates from multiple
    # countries. Auto-pin the country payload predicate when the
    # caller passed a specific region id; respect any explicit
    # ``country`` already in ``filters`` so callers can override the
    # auto-pin (e.g. cross-language search where they want all the
    # German rates regardless of region).
    merged_filters: dict[str, Any] = dict(filters or {})
    if "country" not in merged_filters:
        auto_country = country_filter_for(country)
        if auto_country:
            merged_filters["country"] = auto_country
    qdrant_filter = _build_filter(merged_filters)

    # Encode both queries in one forward pass when resources_query is set.
    texts = [core_query]
    if resources_query:
        texts.append(resources_query)
    encoded = _encode(texts)
    core_dense = encoded["dense"][0]
    core_sparse = encoded["sparse"][0]
    res_dense = encoded["dense"][1] if resources_query else None

    from qdrant_client.http.models import (
        Fusion,
        FusionQuery,
        Prefetch,
    )

    prefetch: list[Prefetch] = [
        Prefetch(
            query=core_dense,
            using="dense",
            filter=qdrant_filter,
            limit=prefetch_limit,
        ),
        Prefetch(
            query=core_sparse,
            using="sparse",
            filter=qdrant_filter,
            limit=prefetch_limit,
        ),
    ]
    if res_dense is not None:
        prefetch.append(
            Prefetch(
                query=res_dense,
                using="resources",
                filter=qdrant_filter,
                limit=prefetch_limit,
            )
        )

    client = _get_client()
    response = client.query_points(
        collection_name=collection,
        prefetch=prefetch,
        query=FusionQuery(fusion=Fusion.RRF),
        with_payload=True,
        with_vectors=False,
        limit=limit,
    )

    hits: list[QdrantHit] = []
    for point in response.points:
        payload = point.payload or {}
        rate_code = str(payload.get("rate_code") or point.id)
        hits.append(
            QdrantHit(
                rate_code=rate_code,
                country=str(payload.get("country", country)),
                score=float(point.score or 0.0),
                payload=dict(payload),
            )
        )
    return hits


async def lookup_full_rows(
    *,
    country: str,
    rate_codes: list[str],
) -> list[dict[str, Any]]:
    """Attach the 84-column parquet data to a list of rate codes.

    Thin proxy onto :mod:`app.modules.costs.parquet_lookup` so the
    ranker stays on a single ``qdrant_adapter`` import. Returns rows in
    the same order as ``rate_codes`` — codes that don't match in the
    parquet are dropped silently (the caller can re-correlate by
    ``rate_code`` if order matters).
    """

    from app.modules.costs.parquet_lookup import lookup_rows

    return await lookup_rows(country=country, rate_codes=rate_codes)


# ── v3-P7: Search hardening ──────────────────────────────────────────────
#
# A naive ``search()`` against the indexed CWICR collections will under-
# return when the SearchPlan emits too many hard filters at once. The
# fallback ladder, dedup pass, and abstract-substitution step below turn
# the raw Qdrant call into a robust top-K builder for the ranker.
#
# Per MAPPING_PROCESS.md v3 §5.2 the relaxation order trades the most
# specific signals first (``ifc_predefined_type``, ``construction_stage``)
# and keeps the bedrock predicates (``country``, ``unit_dim``,
# ``ifc_class``, ``is_abstract=False``) until last — those define the
# "this rate is in the right ballpark" baseline. The Pset booleans are
# dropped together because they are highly correlated and dropping just
# one rarely opens a meaningful new candidate set.

# Filter keys removed at each tier — earlier tiers preserve more
# specificity, later tiers progressively strip down to the bedrock.
# A ``None`` entry means "no relaxation" (final tier yields the full
# original filter set).
_RELAX_TIERS: tuple[tuple[str, ...], ...] = (
    (),                                                       # tier 0 — full filter set
    ("ifc_predefined_type",),                                  # tier 1 — drop subtype
    ("ifc_predefined_type", "construction_stage"),             # tier 2 — drop stage too
    ("ifc_predefined_type", "construction_stage",
     "is_external", "is_loadbearing", "is_structural"),        # tier 3 — drop Psets
    ("ifc_predefined_type", "construction_stage",
     "is_external", "is_loadbearing", "is_structural",
     "department_code", "subsection_code"),                    # tier 4 — drop trade bucket
    ("ifc_predefined_type", "construction_stage",
     "is_external", "is_loadbearing", "is_structural",
     "department_code", "subsection_code", "unit_dim"),        # tier 5 — drop unit dim
)


# Defensive unit-dim aliasing for sources that haven't migrated to the
# canonical ``unit_dim`` enum (m, m2, m3, kg, pcs, lsum). The values
# here are the *canonical* form returned to the ranker so downstream
# boost / dedup logic can rely on a single representation.
_UNIT_DIM_ALIASES: dict[str, str] = {
    "m³": "m3", "м³": "m3", "cubic_meter": "m3", "cubic_metre": "m3",
    "m²": "m2", "м²": "m2", "square_meter": "m2", "square_metre": "m2",
    "m": "m", "м": "m", "linear_meter": "m", "linear_metre": "m",
    "kg": "kg", "кг": "kg", "kilogram": "kg",
    "t": "t", "ton": "t", "tonne": "t", "tonnes": "t", "т": "t",
    "pcs": "pcs", "шт": "pcs", "piece": "pcs", "pieces": "pcs", "stk": "pcs",
    "lsum": "lsum", "ls": "lsum", "lump_sum": "lsum",
}


def _normalise_unit_dim(value: str | None) -> str | None:
    """Return the canonical ``unit_dim`` form or ``None`` for empty input.

    Lookup is case-insensitive and tolerant of typographic variants
    (``m³`` vs ``m3``, Cyrillic ``м²``). Unknown values are returned
    verbatim — the parquet/Qdrant payload may use a vendor-specific
    unit that the alias table doesn't yet know, and we'd rather pin
    that filter than silently drop it.
    """

    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    return _UNIT_DIM_ALIASES.get(raw, raw)


def _dedup_hits(hits: list[QdrantHit]) -> list[QdrantHit]:
    """Drop duplicate ``rate_code`` rows, keeping the highest score.

    Duplicates surface in two situations:

    1. Cross-language fan-out (planned for v3-P8 ``base_code`` rollup) —
       the same rate code appears in DE+EN+RU collections and we want
       only the top-scoring representative.
    2. Defensive coding for collections that accidentally hold both an
       abstract section header and an alias row keyed by the same
       ``rate_code`` (a known pre-v3 data quality issue).

    Order is preserved: the first occurrence wins, so the caller's
    sort order is respected.
    """

    seen: set[str] = set()
    out: list[QdrantHit] = []
    for h in hits:
        if h.rate_code in seen:
            continue
        seen.add(h.rate_code)
        out.append(h)
    return out


def _filters_after_relax(
    filters: dict[str, Any] | None, drop_keys: tuple[str, ...]
) -> dict[str, Any]:
    """Return a shallow copy of ``filters`` with ``drop_keys`` removed.

    Used by :func:`search_with_fallback` to walk the relax ladder
    without mutating the caller's dict — pure-function semantics make
    the tier sequence trivially testable.
    """

    if not filters:
        return {}
    return {k: v for k, v in filters.items() if k not in drop_keys}


# ── v3-P8: Cross-language identity via base_code() ────────────────────────
#
# A CWICR rate code carries optional metadata suffixes:
#
#     03.330.10.de.m3
#     │  │   │  │  └─ unit suffix (one of canonical _UNIT_DIM_ALIASES values)
#     │  │   │  └──── language suffix (ISO-639-1 from REGION_LANGUAGE)
#     │  │   └─────── item ordinal
#     │  └─────────── subsection
#     └────────────── department
#
# The "base code" strips up to two trailing dotted segments where each
# segment is either a known language tag or a canonical unit_dim. This
# lets the ranker dedup the same logical rate across language collections
# (a German wall rate and its English translation share the same base
# code even though they live in different Qdrant collections).
#
# Codes without recognisable suffixes pass through unchanged so non-CWICR
# catalogues — BR SINAPI numeric codes, vendor-specific BYO rates — are
# never accidentally truncated.


def _canonical_unit_dims() -> set[str]:
    """Return the canonical unit_dim set used as suffix sentinels.

    Built from :data:`_UNIT_DIM_ALIASES` *values* (the canonical forms),
    not keys (the alias spellings). Computed lazily so the module import
    stays cheap.
    """
    return set(_UNIT_DIM_ALIASES.values())


def _known_language_tags() -> set[str]:
    """Return ISO-639-1 tags known to :mod:`region_language`.

    Pulls from REGION_LANGUAGE values + bare-country override values so
    every language we route a collection to is recognised as a valid
    suffix sentinel. Imported lazily to keep this adapter independent of
    region_language at import time (circular-import insurance).
    """
    from app.core.match_service.region_language import (
        _BARE_COUNTRY_OVERRIDES,
        REGION_LANGUAGE,
    )

    return set(REGION_LANGUAGE.values()) | set(_BARE_COUNTRY_OVERRIDES.values())


def base_code(rate_code: str | None) -> str:
    """Strip ``.{lang}`` and ``.{unit}`` suffixes for cross-language dedup.

    Walks the dotted segments from the right end and removes a segment
    iff it matches a known language tag or canonical unit_dim. Stops at
    the first non-matching segment so the structural prefix
    (``department.subsection.item``) is preserved verbatim.

    Examples (using the canonical unit set m/m2/m3/kg/t/pcs/lsum and the
    full REGION_LANGUAGE language set)::

        base_code("03.330.10.de.m3")  → "03.330.10"
        base_code("03.330.10.m3.de")  → "03.330.10"        # order-agnostic
        base_code("03.330.10.de")     → "03.330.10"        # only lang
        base_code("03.330.10.m3")     → "03.330.10"        # only unit
        base_code("03.330.10")        → "03.330.10"        # bare prefix
        base_code("87437")            → "87437"            # SINAPI numeric
        base_code("CUSTOM-XYZ")       → "CUSTOM-XYZ"       # BYO vendor code
        base_code("03.330.10.xx.yy")  → "03.330.10.xx.yy"  # unknown suffixes

    Returns the empty string for a falsy input — callers feed ``payload
    .get("rate_code")`` directly without a None-check.
    """

    if not rate_code:
        return ""

    sentinels = _canonical_unit_dims() | _known_language_tags()
    parts = str(rate_code).split(".")

    # Strip up to TWO suffix segments — one lang, one unit (or two of
    # the same kind, defensively, e.g. ``.de.de`` from a buggy seed).
    # Stop at the first non-sentinel so structural codes survive.
    stripped = 0
    while stripped < 2 and len(parts) > 1 and parts[-1].lower() in sentinels:
        parts.pop()
        stripped += 1

    return ".".join(parts)


def _dedup_hits_by_base_code(hits: list[QdrantHit]) -> list[QdrantHit]:
    """Cross-language dedup: keep the highest-score representative per base code.

    Cross-language fan-out (querying ``cwicr_de_v3`` AND ``cwicr_en_v3``
    for a translation-aware project) surfaces the same logical rate
    twice. This collapses them keeping the version that scored highest
    in RRF — typically the one whose collection's language matches the
    user's query language, which is the desired UX.

    Differs from :func:`_dedup_hits` by grouping on ``base_code`` rather
    than the full ``rate_code``: ``03.330.10.de.m3`` and
    ``03.330.10.en.m3`` map to the same key ``03.330.10``.

    First-seen-highest-scored wins — assumes the input is sorted by
    score descending (RRF output already is).
    """

    seen_bases: dict[str, QdrantHit] = {}
    for h in hits:
        key = base_code(h.rate_code) or h.rate_code
        existing = seen_bases.get(key)
        if existing is None or h.score > existing.score:
            seen_bases[key] = h

    # Preserve original input order among the survivors so the caller's
    # RRF rank is respected (not re-sorted).
    seen: set[int] = set()
    out: list[QdrantHit] = []
    for h in hits:
        key = base_code(h.rate_code) or h.rate_code
        if id(seen_bases[key]) in seen:
            continue
        if seen_bases[key] is h:
            seen.add(id(h))
            out.append(h)
    return out


async def cross_language_search(
    *,
    primary_country: str,
    additional_countries: list[str],
    core_query: str,
    resources_query: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 30,
    prefetch_limit: int = 50,
) -> list[QdrantHit]:
    """Fan-out :func:`search` across multiple language collections, dedup by base code.

    The primary country's collection is queried first so its rates anchor
    the result list — if a base code is shared between primary and
    additional collections, the primary-language version wins (assuming
    its score is competitive; the dedup is highest-score-wins).

    ``additional_countries`` is a list of region/country codes to also
    probe. Empty list (default) is equivalent to a single :func:`search`
    call against ``primary_country``.

    The fan-out is parallelised — one ``asyncio.gather`` so total latency
    is dominated by the slowest collection, not the sum.

    Returns up to ``limit`` deduped hits. Results across collections
    aren't re-ranked: the primary collection's ranking is preserved
    until the additional collections contribute genuinely new bases.
    """

    import asyncio

    countries = [primary_country, *additional_countries]
    # De-dup the country list itself — a caller might pass DE_BERLIN
    # twice or include the primary in additional by mistake. Preserve
    # order so the primary stays first.
    seen_countries: set[str] = set()
    unique_countries: list[str] = []
    for c in countries:
        coll = country_to_collection(c) if c else ""
        if coll and coll not in seen_countries:
            seen_countries.add(coll)
            unique_countries.append(c)

    if not unique_countries:
        return []

    coros = [
        search(
            country=c,
            core_query=core_query,
            resources_query=resources_query,
            filters=filters,
            limit=limit,
            prefetch_limit=prefetch_limit,
        )
        for c in unique_countries
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)

    merged: list[QdrantHit] = []
    for c, res in zip(unique_countries, results, strict=False):
        if isinstance(res, Exception):
            logger.debug("cross_language_search: %s failed (%s)", c, res)
            continue
        merged.extend(res)

    deduped = _dedup_hits_by_base_code(merged)
    return deduped[:limit]


def _enumerate_target_codes(base: str, target_country: str) -> list[str]:
    """Enumerate plausible ``rate_code`` variants for ``base`` in ``target_country``.

    Used by :func:`cross_lang_lookup` to translate a rate code from one
    language collection to its sibling in another. The CWICR encoder
    appends ``.{lang}`` and / or ``.{unit}`` suffixes when it materialises
    per-language code variants — but the suffix order, presence, and
    cardinality vary across regions and snapshot vintages. Rather than
    hard-code one shape we enumerate every plausible permutation and let
    Qdrant's ``MatchAny`` resolve it in a single round-trip.

    The output is bounded: 1 (bare) + 1 (lang) + N units + N (lang.unit) +
    N (unit.lang) ≤ 2 + 3·|units|. With the canonical 7-element unit set
    that's at most 23 variants — well within Qdrant's payload-match cap.
    """

    from app.core.match_service.region_language import language_for

    target_lang = (language_for(target_country) or "").lower()
    units = sorted(_canonical_unit_dims())

    out: list[str] = [base]
    if target_lang:
        out.append(f"{base}.{target_lang}")
    for u in units:
        out.append(f"{base}.{u}")
        if target_lang:
            out.append(f"{base}.{target_lang}.{u}")
            out.append(f"{base}.{u}.{target_lang}")
    return out


async def cross_lang_lookup(
    *,
    source_rate_code: str,
    target_country: str,
) -> str | None:
    """Translate a rate_code into the ``target_country``'s language variant.

    Implements MAPPING_PROCESS.md §6.2 "точный подход" (exact approach):
    when a project's documentation is in EN but the estimate must be in
    RU rates, we want the *same* logical rate as a RU code with RU
    prices, not just a multilingual fan-out (which would surface the EN
    rate dressed in RU clothing).

    Algorithm:

    1. Strip ``.{lang}.{unit}`` suffixes from ``source_rate_code`` via
       :func:`base_code`. ``"03.330.10.en.m3"`` → ``"03.330.10"``.
    2. Enumerate plausible target-language variants
       (:func:`_enumerate_target_codes`).
    3. Single Qdrant scroll on ``country_to_collection(target_country)``
       with ``MatchAny`` on ``rate_code`` — at most one round-trip.
    4. When the target language collection mixes regions (ES collection
       carries ES + MX + AR), narrow further with the
       :func:`country_filter_for` predicate so the lookup honours the
       caller's region pin.

    Returns the matching ``rate_code`` string when found, else ``None``.
    Defensive: degrades to ``None`` on any Qdrant error / missing extras
    rather than raising, so the caller can fall back to semantic search.

    Examples::

        await cross_lang_lookup(
            source_rate_code="03.330.10.en.m3",
            target_country="RU_MOSCOW",
        )
        # → "03.330.10.ru.m3"  (or whatever the RU snapshot uses)

        await cross_lang_lookup(
            source_rate_code="FER46-01-001",
            target_country="DE_BERLIN",
        )
        # → None  (FER codes have no DE counterpart)
    """

    if not source_rate_code or not target_country:
        return None

    base = base_code(source_rate_code)
    if not base:
        return None

    coll = country_to_collection(target_country)
    if not coll:
        return None

    candidates = _enumerate_target_codes(base, target_country)

    try:
        from qdrant_client.http.models import (  # noqa: PLC0415
            FieldCondition,
            Filter,
            MatchAny,
            MatchValue,
        )

        client = _get_client()
        must: list[FieldCondition] = [
            FieldCondition(key="rate_code", match=MatchAny(any=candidates)),
        ]
        country_pin = country_filter_for(target_country)
        if country_pin:
            must.append(
                FieldCondition(key="country", match=MatchValue(value=country_pin)),
            )

        # Sync qdrant_client.scroll — mirrors the pattern used by
        # :func:`search` (see ``client.query_points`` callsite).
        points, _next = client.scroll(
            collection_name=coll,
            scroll_filter=Filter(must=must),
            limit=1,
            with_payload=["rate_code"],
            with_vectors=False,
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug(
            "cross_lang_lookup: %r → %s lookup failed: %s",
            source_rate_code,
            target_country,
            exc,
        )
        return None

    if not points:
        return None

    found = str(points[0].payload.get("rate_code") or "").strip()
    return found or None


async def search_with_fallback(
    *,
    country: str,
    core_query: str,
    resources_query: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 30,
    prefetch_limit: int = 50,
    min_results: int | None = None,
) -> tuple[list[QdrantHit], int]:
    """Hardened :func:`search` with relax-tier fallback and dedup.

    Walks :data:`_RELAX_TIERS` until the result set has at least
    ``min_results`` hits or the bedrock filters are reached. Returns
    ``(hits, tier_used)`` so the caller can log which tier earned the
    candidates — useful for v3-P10 analytics on filter-set tightness.

    ``min_results`` defaults to ``max(1, limit // 4)`` — i.e., we try
    to keep at least a quarter of the requested limit. Setting it to
    ``limit`` forces full relaxation; setting it to ``0`` disables
    fallback entirely (single tier-0 call).
    """

    threshold = min_results if min_results is not None else max(1, limit // 4)
    last_hits: list[QdrantHit] = []
    last_tier = 0
    for tier_idx, drop_keys in enumerate(_RELAX_TIERS):
        relaxed = _filters_after_relax(filters, drop_keys)
        hits = await search(
            country=country,
            core_query=core_query,
            resources_query=resources_query,
            filters=relaxed,
            limit=limit,
            prefetch_limit=prefetch_limit,
        )
        deduped = _dedup_hits(hits)
        last_hits = deduped
        last_tier = tier_idx
        if len(deduped) >= threshold:
            if tier_idx > 0:
                logger.info(
                    "qdrant_adapter: relaxed to tier %d (dropped %s) for %d hits",
                    tier_idx,
                    drop_keys,
                    len(deduped),
                )
            return deduped, tier_idx
    return last_hits, last_tier


async def substitute_abstract_parents(
    *,
    country: str,
    core_query: str,
    hits: list[QdrantHit],
    max_substitutions: int = 2,
    children_per_parent: int = 3,
) -> list[QdrantHit]:
    """Replace ``is_abstract=True`` rows with concrete children.

    Section headers (e.g., DIN 276 KG-330 "Außenwände") are valuable
    semantically — the dense vector hits them when the query is broad —
    but worthless as cost rates because they have no unit price. v3
    indexes them with ``is_abstract=True`` so the ranker can spot them
    and issue a narrow follow-up search constrained to the same
    ``department_code`` / ``subsection_code`` with ``is_abstract=False``.

    Only the top ``max_substitutions`` abstract hits trigger follow-ups
    so the latency cost stays bounded (each follow-up is one Qdrant
    Query API call). Concrete children are spliced in at the abstract
    parent's original rank position; their order among themselves is
    the RRF order returned by the follow-up call.

    Hits without an abstract row pass through unchanged.
    """

    if not hits:
        return hits

    out: list[QdrantHit] = []
    substitutions_done = 0
    seen_codes: set[str] = {h.rate_code for h in hits if not h.payload.get("is_abstract")}

    for hit in hits:
        if not hit.payload.get("is_abstract"):
            out.append(hit)
            continue
        if substitutions_done >= max_substitutions:
            # Past the budget — keep the abstract as-is so the caller
            # at least knows there's a section-header candidate.
            out.append(hit)
            continue

        # Build a follow-up filter that pins the same trade bucket but
        # excludes the section header. ``subsection_code`` is preferred
        # when present (more specific); fall back to ``department_code``.
        sub_filters: dict[str, Any] = {"is_abstract": False}
        sub_code = hit.payload.get("subsection_code")
        dept_code = hit.payload.get("department_code")
        if sub_code:
            sub_filters["subsection_code"] = sub_code
        elif dept_code:
            sub_filters["department_code"] = dept_code
        else:
            # No trade bucket to narrow on → keep the abstract as-is.
            out.append(hit)
            continue

        try:
            children = await search(
                country=country,
                core_query=core_query,
                filters=sub_filters,
                limit=children_per_parent,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("substitute_abstract_parents: follow-up failed (%s)", exc)
            out.append(hit)
            continue

        added_any = False
        for child in children:
            if child.rate_code in seen_codes:
                continue
            seen_codes.add(child.rate_code)
            out.append(child)
            added_any = True

        if not added_any:
            # Children were all dupes of existing concrete hits — keep
            # the abstract so the caller can decide what to do.
            out.append(hit)
        substitutions_done += 1

    return out


__all__ = [
    "QdrantHit",
    "base_code",
    "country_filter_for",
    "country_to_collection",
    "cross_lang_lookup",
    "cross_language_search",
    "lookup_full_rows",
    "search",
    "search_with_fallback",
    "substitute_abstract_parents",
]
