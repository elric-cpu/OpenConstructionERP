# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Single source of truth for region/catalogue → language mapping.

Two callsites historically maintained their own copy of this mapping:

    * ``app.modules.costs.vector_adapter._REGION_LANGUAGE`` — used to
      stamp every CWICR row with its dominant language during the
      LanceDB upsert and to filter results by language at query time.
    * ``app.core.match_service.ranker._CATALOG_LANGUAGE`` — used by the
      translation cascade to rewrite the user's BIM-element name into
      the catalogue's native language before the vector search.

These tables drifted (UK_GBP vs GB_LONDON, CS_PRAGUE vs CZ_PRAGUE,
SP_BARCELONA vs ES_MADRID, ENG_TORONTO vs CA_TORONTO, etc.) which broke
the translation cascade for any catalogue id that lived in only one of
the two tables. This module hoists both into one canonical mapping so
the next addition can never silently regress.

Public API:

    * ``REGION_LANGUAGE`` — canonical dict of catalogue id → ISO-639-1.
      Use this for membership tests when a callsite needs to enumerate
      known regions (rare).
    * ``language_for(code)`` — resolve any region or catalogue id to a
      language tag. Handles historical aliases and falls back to
      ``"en"`` so search ranking still works on rows whose language
      we couldn't infer.
"""

from __future__ import annotations

# Canonical region/catalogue IDs. Keys here MUST be the form used by:
#   - the parquet/CSV ``region`` column we ship in CWICR seed data
#   - the ``project.cost_database_id`` catalogue picker
#
# Add new regions HERE. If a tenant has loaded a catalogue under a
# non-canonical id, register the alias in ``_ALIASES`` below — do not
# duplicate the entry here. Otherwise the next maintainer can't tell
# which id is canonical.
REGION_LANGUAGE: dict[str, str] = {
    # German-speaking (DACH)
    "DE_BERLIN": "de",
    "DE_MUNICH": "de",
    "DE_HAMBURG": "de",
    "AT_VIENNA": "de",
    "CH_ZURICH": "de",
    # Romance
    "FR_PARIS": "fr",
    "ES_MADRID": "es",
    "IT_ROME": "it",
    "PT_LISBON": "pt",
    "BR_SAOPAULO": "pt",
    "PT_SAOPAULO": "pt",        # legacy id, retained for back-compat
    # English / Anglophone
    "GB_LONDON": "en",
    "IE_DUBLIN": "en",
    "USA_USD": "en",
    "USA_NEWYORK": "en",
    "CA_TORONTO": "en",
    "AU_SYDNEY": "en",
    "NZ_AUCKLAND": "en",
    "ZA_JOHANNESBURG": "en",
    "NG_LAGOS": "en",
    "IN_MUMBAI": "en",
    # Slavic / CIS
    "PL_WARSAW": "pl",
    "CZ_PRAGUE": "cs",
    "RO_BUCHAREST": "ro",
    "RU_STPETERSBURG": "ru",
    "RU_MOSCOW": "ru",
    "BG_SOFIA": "bg",
    "LT_VILNIUS": "lt",
    "HR_ZAGREB": "hr",
    # Benelux
    "NL_AMSTERDAM": "nl",
    "BE_BRUSSELS": "nl",
    # Nordic
    "SV_STOCKHOLM": "sv",
    # Asia / MENA
    "CN_SHANGHAI": "zh",
    "JP_TOKYO": "ja",
    "KR_SEOUL": "ko",
    "ID_JAKARTA": "id",
    "TH_BANGKOK": "th",
    "VN_HANOI": "vi",
    "AE_DUBAI": "ar",
    "SA_RIYADH": "ar",
    "TR_ISTANBUL": "tr",
    "HI_MUMBAI": "hi",
    # LatAm
    "MX_MEXICO": "es",
    "MX_MEXICOCITY": "es",
    "AR_BUENOSAIRES": "es",
}


# Historical aliases. Old projects loaded their catalogues under these
# ids before the canonical naming convention settled. Keep them working
# until a one-time migration renames them to the canonical id at the DB
# level. Each alias must point to a key in ``REGION_LANGUAGE`` above.
_ALIASES: dict[str, str] = {
    "UK_GBP": "GB_LONDON",       # used by an early UK rate import
    "ENG_TORONTO": "CA_TORONTO", # mis-prefixed in a 2025 batch
    "SP_BARCELONA": "ES_MADRID", # ES is the ISO code; SP was a typo
    "CS_PRAGUE": "CZ_PRAGUE",    # CS is the language code, not country
    "ZH_SHANGHAI": "CN_SHANGHAI",# language-prefixed catalogue id
    "JA_TOKYO": "JP_TOKYO",
    "KO_SEOUL": "KR_SEOUL",
    "VI_HANOI": "VN_HANOI",
    "AR_DUBAI": "AE_DUBAI",
}


# Bare ISO-3166 alpha-2 country code → language tag, derived from
# REGION_LANGUAGE at module load. ``"DE"`` resolves via the first
# ``DE_*`` key (deterministic dict iteration since Python 3.7), so
# ``language_for("DE")`` returns ``"de"`` without the caller having to
# know which city is canonical. Built once at import — the underlying
# REGION_LANGUAGE never mutates at runtime.
#
# This solves a v3-collection-naming corner: catalogues stored as bare
# country codes (an early CWICR shipping convention before the
# ``COUNTRY_CITY`` form settled) used to land in ``cwicr_en_v3`` because
# ``"DE"`` had no direct REGION_LANGUAGE hit. With the head-fallback
# they correctly route to their language collection.
_HEAD_LANGUAGE: dict[str, str] = {}
for _key, _lang in REGION_LANGUAGE.items():
    _head = _key.split("_", 1)[0]
    _HEAD_LANGUAGE.setdefault(_head, _lang)
del _key, _lang, _head


# Country codes whose ISO-3166 letters happen to clash with ISO-639
# language codes — explicit overrides so the country interpretation
# wins. ``AR`` is Argentina (es) not Arabic; ``ID`` is Indonesia (id);
# ``HR`` is Croatia (hr); etc. Most of these resolve identically via
# the head fallback because the matching ``COUNTRY_CITY`` row already
# carries the right language, but pinning them explicitly makes the
# intent unambiguous to the next maintainer who reads ``language_for``.
_BARE_COUNTRY_OVERRIDES: dict[str, str] = {
    "AR": "es",      # Argentina (Buenos Aires) — not Arabic
    "BG": "bg",      # Bulgaria
    "BR": "pt",      # Brazil
    "CN": "zh",      # China
    "CZ": "cs",      # Czech Republic — language is cs, not cz
    "GB": "en",      # United Kingdom — historical British alias
    "HR": "hr",      # Croatia
    "ID": "id",      # Indonesia
    "JP": "ja",      # Japan
    "KR": "ko",      # Korea
    "RO": "ro",      # Romania
    "TH": "th",      # Thailand
    "TR": "tr",      # Turkey
    "VN": "vi",      # Vietnam
    "AE": "ar",      # United Arab Emirates speaks Arabic
    "SA": "ar",      # Saudi Arabia speaks Arabic
    "USA": "en",     # 3-letter US alias still in use by some catalogues
}


def language_for(code: str | None) -> str:
    """Return the dominant ISO-639-1 language tag for a region or catalogue id.

    Resolution order:

        1. Direct hit in :data:`REGION_LANGUAGE` (full ``COUNTRY_CITY``).
        2. Alias resolved through :data:`_ALIASES` then re-looked-up.
        3. Explicit bare-country override in :data:`_BARE_COUNTRY_OVERRIDES`.
        4. Head fallback: take the prefix before ``_`` and consult the
           auto-built :data:`_HEAD_LANGUAGE` map (``"DE"`` → ``"de"``,
           ``"DE_BREMEN"`` → ``"de"`` even though the row isn't in the
           canonical table yet).
        5. ``"en"`` fallback — search ranking still works without a
           translation pass; we just lose the cross-lingual signal.

    The lookup is case-insensitive on the input but case-sensitive on
    the table (matching the historical ``UPPER`` storage convention).
    """
    if not code:
        return "en"
    key = code.strip().upper()
    if not key:
        return "en"
    if key in REGION_LANGUAGE:
        return REGION_LANGUAGE[key]
    canonical = _ALIASES.get(key)
    if canonical and canonical in REGION_LANGUAGE:
        return REGION_LANGUAGE[canonical]
    if key in _BARE_COUNTRY_OVERRIDES:
        return _BARE_COUNTRY_OVERRIDES[key]
    head = key.split("_", 1)[0]
    if head != key:
        # ``DE_BREMEN`` — try resolving the head only.
        if head in REGION_LANGUAGE:
            return REGION_LANGUAGE[head]
        if head in _BARE_COUNTRY_OVERRIDES:
            return _BARE_COUNTRY_OVERRIDES[head]
        if head in _HEAD_LANGUAGE:
            return _HEAD_LANGUAGE[head]
    elif key in _HEAD_LANGUAGE:
        return _HEAD_LANGUAGE[key]
    return "en"


def country_head(code: str | None) -> str | None:
    """Extract the ISO-3166-ish country prefix from a region/catalogue id.

    ``"DE_BERLIN"`` → ``"DE"``; ``"USA_USD"`` → ``"USA"``;
    ``"de"`` → ``"DE"`` (case-normalised). Returns ``None`` when the
    input is empty so callers can drop the country payload filter for
    "search across all countries within this language".

    Used by :mod:`app.modules.costs.qdrant_adapter` to populate the
    ``country`` payload predicate when a single language collection
    holds rates from multiple regions (e.g. ``cwicr_es_v3`` carries
    Spain, Mexico, Argentina) and the project picked one specific
    catalogue.
    """
    if not code:
        return None
    key = code.strip().upper()
    if not key:
        return None
    head = key.split("_", 1)[0]
    return head or None


__all__ = ["REGION_LANGUAGE", "country_head", "language_for"]
