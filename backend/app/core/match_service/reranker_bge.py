# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""‌⁠‍Local BGE cross-encoder rerank tier — free, fast, gracefully degrades.

The bi-encoder + RRF fusion path in :mod:`qdrant_adapter` is fast but
noisy at the boundary between rank 1 and rank 5: the top candidates
have very similar fused scores so small lexical differences (concrete
grade ``C30/37`` vs ``C25/30``) get smoothed out. A cross-encoder
re-scores ``(query, candidate)`` pairs *together* through one transformer
forward pass — substantially better at fine discrimination.

Where this differs from :mod:`reranker_ai`:

* No API cost — runs locally on CPU (or GPU when present).
* No latency budget tradeoff — INT8 ONNX BGE-reranker-v2-m3 reranks
  10 pairs in ~200 ms on a typical VPS, well under the user-facing
  budget.
* No external dependency at import time — :func:`rerank` lazy-imports
  ``FlagEmbedding.FlagReranker`` and falls through cleanly when the
  ``[semantic]`` extra is missing.

The bge variant is **not** opt-in like the LLM reranker — it runs on
every match request once enabled in settings. The opt-out is via
``settings.match_use_bge_reranker = False`` for installs where the
extra disk footprint (~568 MB FP32, ~140 MB INT8) is too much.

Model selection follows :data:`RERANK_BGE_MODEL_NAME` from
:mod:`config`. Default is ``BAAI/bge-reranker-v2-m3`` — multilingual
across 100+ languages, MIT-licensed, same author as ``bge-m3`` so
cross-encoder ↔ bi-encoder are trained on the same corpus.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.match_service.envelope import (
    ElementEnvelope,
    MatchCandidate,
    confidence_band_for,
)

logger = logging.getLogger(__name__)


# Cached reranker instance — the model is large enough that re-loading
# it per-request would dominate latency. None until first successful
# load; ``False`` after a load failure to short-circuit subsequent
# attempts (no point retrying on every match).
_RERANKER: Any = None


def _get_reranker() -> Any:
    """Lazy-load and cache the FlagReranker model.

    Returns the cached reranker instance, or ``None`` if the
    ``[semantic]`` extra isn't installed / the model couldn't be
    fetched. Subsequent calls after a failure return ``None`` cheaply
    without re-attempting the import.
    """
    global _RERANKER
    if _RERANKER is False:
        return None
    if _RERANKER is not None:
        return _RERANKER

    try:
        from FlagEmbedding import FlagReranker  # type: ignore[import-not-found]
    except ImportError:
        logger.info("reranker_bge: FlagEmbedding not installed — rerank disabled")
        _RERANKER = False
        return None

    from app.config import get_settings

    settings = get_settings()
    model_name = getattr(settings, "rerank_bge_model_name", "BAAI/bge-reranker-v2-m3")
    use_fp16 = bool(getattr(settings, "rerank_bge_use_fp16", False))

    try:
        _RERANKER = FlagReranker(model_name, use_fp16=use_fp16)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("reranker_bge: model load failed (%s) — rerank disabled", exc)
        _RERANKER = False
        return None
    return _RERANKER


def _build_query_text(envelope: ElementEnvelope) -> str:
    """Render the envelope into a single query string for the cross-encoder.

    Mirrors the ``core_query`` from :func:`query_builder.build_search_plan`
    so the reranker sees the same semantic signal the bi-encoder did.
    Kept narrow on purpose — the cross-encoder benefits from a short
    focused query, not a noisy concatenation.
    """
    parts: list[str] = []
    if envelope.category:
        parts.append(str(envelope.category))
    if envelope.description:
        parts.append(str(envelope.description))
    if envelope.material_class:
        parts.append(str(envelope.material_class))
    if envelope.nominal_size_mm:
        parts.append(f"{envelope.nominal_size_mm}mm")
    if envelope.unit_hint:
        parts.append(str(envelope.unit_hint))
    return " ".join(p.strip() for p in parts if p.strip())


def _build_candidate_text(candidate: MatchCandidate) -> str:
    """Render the candidate into the cross-encoder's "passage" half.

    Cross-encoders score (query, passage) jointly so the passage must
    carry the discriminating signal — code, description, unit. Skip
    fields the bi-encoder already scored (vector_score) since the
    cross-encoder isn't operating on the embedding.
    """
    parts: list[str] = []
    if candidate.code:
        parts.append(str(candidate.code))
    if candidate.description:
        parts.append(str(candidate.description))
    if candidate.unit:
        parts.append(f"unit {candidate.unit}")
    return " ".join(p.strip() for p in parts if p.strip())


def _normalize_bge_scores(raw_scores: list[float]) -> list[float]:
    """Map FlagReranker logits onto the [0,1] band the rest of the system expects.

    BGE-reranker outputs unbounded logits, typically in the range
    [-10, +10]. Apply a sigmoid so downstream :func:`confidence_band_for`
    can compare them against the existing thresholds without rescaling.
    """
    import math

    return [1.0 / (1.0 + math.exp(-s)) for s in raw_scores]


def is_available() -> bool:
    """Return ``True`` when the BGE reranker can be invoked.

    Cheap probe — calls :func:`_get_reranker` and observes the cache
    state. Intended for callers that want to gate UI ("rerank with BGE"
    toggle) on actual availability rather than a settings flag alone.
    """
    return _get_reranker() is not None


def rerank(
    candidates: list[MatchCandidate],
    envelope: ElementEnvelope,
    *,
    k: int | None = None,
    hard_filters_matched: int = 0,
    classification_confidence_by_code: dict[str, str] | None = None,
) -> list[MatchCandidate]:
    """Re-score the top-``k`` candidates with the local BGE cross-encoder.

    Mutates score + confidence_band on each reranked candidate; never
    re-orders the tail beyond the top-``k`` slice (the bi-encoder is
    trustworthy enough past rank 10 that re-ordering would just churn).

    On any failure path — model not loaded, single empty candidate,
    encoding error — returns the input list unchanged. The caller is
    expected to treat the return value as a possibly-no-op transform.

    ``hard_filters_matched`` and ``classification_confidence_by_code``
    are forwarded into :func:`confidence_band_for` so the v3-P9 §6.4
    band derivation factors in the SearchPlan tightness.
    """

    if not candidates:
        return candidates

    reranker = _get_reranker()
    if reranker is None:
        return candidates

    head_size = k if k is not None else min(len(candidates), 10)
    head = candidates[:head_size]
    tail = candidates[head_size:]

    query = _build_query_text(envelope)
    pairs: list[tuple[str, str]] = [
        (query, _build_candidate_text(c)) for c in head
    ]
    if not query or not all(text for _, text in pairs):
        return candidates

    try:
        raw_scores = reranker.compute_score(pairs)
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("reranker_bge: compute_score failed (%s)", exc)
        return candidates

    if not isinstance(raw_scores, list):
        # FlagReranker returns a float for a single pair; coerce.
        raw_scores = [float(raw_scores)]
    raw_scores = [float(s) for s in raw_scores]
    normalized = _normalize_bge_scores(raw_scores)

    by_code = classification_confidence_by_code or {}
    reranked: list[MatchCandidate] = []
    for cand, new_score in zip(head, normalized, strict=False):
        clamped = max(0.0, min(1.0, new_score))
        band = confidence_band_for(
            clamped,
            hard_filters_matched=hard_filters_matched,
            classification_confidence=by_code.get(cand.code),
        )
        reranked.append(
            cand.model_copy(
                update={
                    "score": clamped,
                    "confidence_band": band,
                    "boosts_applied": {
                        **cand.boosts_applied,
                        "bge_rerank": clamped - cand.score,
                    },
                }
            )
        )

    reranked.sort(key=lambda c: c.score, reverse=True)
    return reranked + tail


__all__ = ["is_available", "rerank"]
