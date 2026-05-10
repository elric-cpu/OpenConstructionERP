# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""‌⁠‍Region boost — rewards candidates from the project's region.

CWICR ships one regional file per market (``DE_BERLIN``, ``GB_LONDON``,
``USA_NEWYORK``, ...). When the project says "DACH" the matcher should
prefer DACH-priced candidates even if a UK candidate has marginally
higher cosine similarity — the unit rate in the wrong region is a
useless number.

This boost is deliberately small (5 %) because regional preference
should bias ties, not override clear semantic mismatches.
"""

from __future__ import annotations

from typing import Any

from app.core.match_service.config import BOOST_WEIGHTS
from app.core.match_service.envelope import ElementEnvelope, MatchCandidate

# Project-region keyword → tuple of CWICR country prefixes the candidate's
# ``region_code`` should start with for a region match.
#
# Two layers, in lookup precedence order:
#
# 1. **Hand-curated multi-country aliases** (``_REGION_GROUP_ALIASES``).
#    These are macro-regions a human picks in the project picker
#    ("DACH" = DE+AT+CH, "UK" = GB+IE) that don't correspond to a single
#    ISO country. They have to be enumerated explicitly.
# 2. **Auto-derived single-country prefixes** from
#    :data:`region_language.REGION_LANGUAGE`. Every country with at
#    least one CWICR catalogue gets a `"<iso>": ("<ISO>_",)` row at
#    import time so a project pinned to ``HR_ZAGREB`` (the CWICR
#    region) or just ``HR`` (bare country code) automatically gets a
#    Croatian-rate boost — without anyone having to remember to add
#    Croatia to a hand-edited table here.
#
# Result: the boost stays consistent with whatever regions the catalogue
# layer knows about. Adding a new country to ``REGION_LANGUAGE`` (e.g. a
# future Vietnam catalogue) needs zero changes in this file.
#
# Two flavours of multi-country alias coexist:
#   - **Geographic** (DACH, UK, Iberia, LATAM, Benelux, Gulf, Scandinavia)
#     group countries by physical proximity. Picked when the operator's
#     supply chain is regionally clustered.
#   - **Language-family** (anglophone, hispanic, lusophone, francophone,
#     germanic, slavic, arabic, nordic) group countries by primary
#     working language. Picked when the operator wants the matcher to
#     consider semantically-equivalent rates from any country sharing
#     the language — e.g. an ES-Madrid project willing to accept MX or
#     AR rates as fallback when ES coverage is thin.
# The two are NOT auto-merged — picking "ES" stays single-country to
# avoid surprise. Operators opt into language coupling explicitly.
_REGION_GROUP_ALIASES: dict[str, tuple[str, ...]] = {
    # ── Geographic ──────────────────────────────────────────────────
    "dach": ("DE_", "AT_", "CH_"),
    "uk": ("GB_", "IE_"),
    "us": ("USA_", "US_"),
    "usa": ("USA_", "US_"),
    "benelux": ("NL_", "BE_", "LU_"),
    "iberia": ("ES_", "PT_"),
    "scandinavia": ("SE_", "SV_", "NO_", "DK_", "FI_"),
    "gulf": ("AE_", "SA_", "QA_", "KW_", "BH_", "OM_"),
    "latam": ("MX_", "BR_", "AR_", "CL_", "CO_", "PE_"),
    # ── Language-family ─────────────────────────────────────────────
    "anglophone": (
        "USA_", "US_", "GB_", "IE_", "AU_", "NZ_", "CA_", "ZA_", "IN_", "NG_",
    ),
    "hispanic": (
        "ES_", "MX_", "AR_", "CL_", "CO_", "PE_", "EC_", "UY_", "PY_",
        "BO_", "DO_", "CR_", "VE_", "GT_", "PA_", "HN_", "SV_", "NI_",
    ),
    "lusophone": ("PT_", "BR_", "AO_", "MZ_", "CV_", "TL_"),
    "francophone": (
        "FR_", "BE_", "CH_", "CA_", "MA_", "TN_", "DZ_", "SN_", "CI_",
        "CM_", "MG_", "CD_", "BF_", "ML_", "GN_", "TG_", "BJ_", "NE_",
        "RW_", "BI_", "DJ_", "GA_", "LU_", "MC_",
    ),
    "germanic": ("DE_", "AT_", "CH_", "LI_"),
    "slavic": (
        "RU_", "UA_", "BY_", "PL_", "CZ_", "SK_", "BG_", "RS_", "HR_",
        "SI_", "MK_", "BA_", "ME_",
    ),
    "arabic": (
        "AE_", "SA_", "QA_", "KW_", "BH_", "OM_", "EG_", "MA_", "TN_",
        "DZ_", "JO_", "LB_", "SY_", "IQ_", "YE_", "PS_", "LY_", "SD_",
    ),
    "nordic": ("SE_", "SV_", "NO_", "DK_", "FI_", "IS_"),
    "turkic": ("TR_", "AZ_", "KZ_", "UZ_", "TM_", "KG_", "TJ_"),
    "sinic": ("CN_", "TW_", "HK_", "SG_"),
}


def _build_country_prefix_table() -> dict[str, tuple[str, ...]]:
    """Auto-derive ``{iso_lower: (PREFIX_,)}`` from REGION_LANGUAGE keys.

    Every distinct head before the first underscore in REGION_LANGUAGE
    becomes its own one-prefix entry. Aliases in ``_BARE_COUNTRY_OVERRIDES``
    that don't appear in REGION_LANGUAGE (e.g. ``CZ`` whose key is
    ``CZ_PRAGUE``) still get covered because both heads route through
    the same iteration.
    """
    from app.core.match_service.region_language import (
        _BARE_COUNTRY_OVERRIDES,
        REGION_LANGUAGE,
    )

    out: dict[str, tuple[str, ...]] = {}
    for key in REGION_LANGUAGE:
        head = key.split("_", 1)[0]
        if head and head.lower() not in out:
            out[head.lower()] = (f"{head}_",)
    for head in _BARE_COUNTRY_OVERRIDES:
        if head.lower() not in out:
            out[head.lower()] = (f"{head}_",)
    return out


_AUTO_COUNTRY_PREFIXES: dict[str, tuple[str, ...]] = _build_country_prefix_table()


def _project_region_prefixes(settings: Any) -> tuple[str, ...]:
    """‌⁠‍Resolve the region-prefix tuple from project / match settings.

    The project's ``region`` field (``"DACH"`` / ``"UK"`` / ``"DE_BERLIN"``)
    is the primary signal; we fold it lowercase and look up the prefix
    table. If the region is already a CWICR ``COUNTRY_CITY`` code we
    return it as-is so a project pinned to ``DE_BERLIN`` only matches
    Berlin-priced rows (no Munich crossover).
    """
    project = getattr(settings, "project", None)
    region_raw: str = ""
    if project is not None:
        region_raw = str(getattr(project, "region", "") or "")
    if not region_raw:
        # ``settings`` itself sometimes carries the region (test stubs).
        region_raw = str(getattr(settings, "region", "") or "")
    if not region_raw:
        return ()

    region = region_raw.strip()
    if "_" in region:
        # Already a fully-qualified CWICR region code (e.g. "DE_BERLIN").
        # Return the *exact* code — a candidate with the same code will
        # match via ``startswith()``. Appending an extra underscore
        # would break the equality case (``"DE_BERLIN".startswith("DE_BERLIN_")``
        # is False). Tuple-form is mandatory — a bare string would be
        # iterated character-by-character downstream.
        upper = region.upper().rstrip("_")
        return (upper,)

    key = region.lower()
    # Group aliases (DACH, UK, Benelux, …) win over single-country
    # prefixes — operators picking "Iberia" expect ES+PT, not just one.
    if key in _REGION_GROUP_ALIASES:
        return _REGION_GROUP_ALIASES[key]
    return _AUTO_COUNTRY_PREFIXES.get(key, ())


def boost(
    envelope: ElementEnvelope,  # noqa: ARG001 — interface symmetry
    candidate: MatchCandidate,
    settings: Any,
) -> dict[str, float]:
    """‌⁠‍Add region-match boost when the candidate's region matches."""
    cand_region = (candidate.region_code or "").strip().upper()
    if not cand_region:
        return {}

    prefixes = _project_region_prefixes(settings)
    if not prefixes:
        return {}

    for prefix in prefixes:
        if cand_region.startswith(prefix.upper()):
            return {"region_match": BOOST_WEIGHTS.region_match}

    return {}
