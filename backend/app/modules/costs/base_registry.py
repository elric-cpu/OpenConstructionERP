"""Single source of truth for the CWICR cost-base catalog.

The public DDC CWICR data repository publishes nine cost-base families. One of
them, the global CWICR base (derived from the GESN / FER / TER norm structure),
is fully built out: its work-item catalogue is localized and repriced into 30
markets and nine languages, and each market ships a complete work-item parquet.
The other eight are authentic national bases built directly from each country's
official norm system (China Dinge, Turkey Birim Fiyat, Brazil SINAPI, Spain
BCCA, Italy Prezzario Regione Toscana, Greece GGDE, Vietnam Dinh Muc, Indonesia
AHSP); each ships one full home-market work-item base.

This module is the one place that knows, for every loadable base, its platform
region id, the GitHub path of its work-item parquet, the folder holding its
resource-catalog CSV, and the work-item ("position") count shown in the base
browser before anything is loaded. Both the cost-item loader
(``app.modules.costs.router``) and the resource-catalog loader
(``app.modules.catalog.router``) resolve their GitHub download paths from here,
and the ``GET /api/v1/costs/base-catalog`` endpoint serializes it, so the three
user surfaces (import page, database setup, onboarding) never drift apart.

The repository was restructured so every market parquet now lives nested under
its national-base parent folder. Keeping the paths here, generated once, means a
future restructure is a one-file change rather than a hunt through three
hardcoded frontend arrays and two backend maps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: ``owner/repo`` slug of the public CWICR data repository.
REPO = "datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR"

#: Repo folder of the flagship global base. Every one of its 30 markets is a
#: full work-item parquet under ``<this>/<XX>___DDC_CWICR/``.
_GLOBAL_BASE_FOLDER = "CIS-Russia-GESN-FER-TER"

#: Number of work items (deduplicated positions) in the global CWICR base. The
#: figure is uniform across all 30 markets because a market is the same
#: catalogue repriced and relabeled, not a different set of works. Sourced from
#: the base's published README (55,719 work items / 27,672 resources).
_GLOBAL_POSITIONS = 55719


@dataclass(frozen=True)
class BaseVariant:
    """One loadable cost base: a full work-item catalogue for a single market.

    Attributes:
        region: Platform region id, the value stored in ``oe_costs_item.region``
            and the ``db_id`` path segment of ``POST /costs/load-cwicr/{db_id}``.
        market: Human market / country label (English).
        city: Representative city or ``"National"`` for country-wide bases.
        language: Display language label (ASCII-friendly, as shown in the UI).
        lang_code: ISO 639-1 language code.
        currency: ISO 4217 currency code the rates are expressed in.
        flag: ISO 3166-1 alpha-2 country code (lowercase) for the flag icon.
        positions: Work-item count shown before load.
        workitems_path: Path of the work-item parquet, relative to the repo raw
            root, used as the GitHub download fallback.
        catalog_folder: Repo folder holding this market's resource-catalog CSV.
        catalog_token: Region token embedded in the catalog CSV file name
            (``DDC_CWICR_<token>_Catalog.csv``); differs from ``region`` for the
            national bases whose export keeps a short country prefix.
        bundled: Whether the base ships locally (loads without any network).
        coefficient: Whether it is a codeless coefficient base (no priced
            resources of its own; estimable via a resource price sheet).
    """

    region: str
    market: str
    city: str
    language: str
    lang_code: str
    currency: str
    flag: str
    positions: int
    workitems_path: str
    catalog_folder: str
    catalog_token: str
    bundled: bool = False
    coefficient: bool = False


@dataclass(frozen=True)
class BaseFamily:
    """A cost-base family: a norm system and the markets available under it.

    Attributes:
        key: Stable machine key (``"global"``, ``"china"``, ...).
        name: Display name of the family.
        norm_system: The official norm / classification the base derives from.
        origin: Origin country label (``"Russia"`` for the flagship global base).
        origin_flag: ISO 3166-1 alpha-2 code for the origin flag.
        description: One-line plain-language summary for the browser.
        variants: Loadable market bases in this family.
        repriceable_markets: Count of additional markets the base can be
            repriced into via resource price sheets (0 when not applicable).
    """

    key: str
    name: str
    norm_system: str
    origin: str
    origin_flag: str
    description: str
    variants: list[BaseVariant] = field(default_factory=list)
    repriceable_markets: int = 0


# ── Global CWICR base: 30 full-work-item markets ────────────────────────────
# (region, XX folder, market, city, language label, lang code, currency, flag)
_GLOBAL_MARKETS: tuple[tuple[str, str, str, str, str, str, str, str], ...] = (
    ("USA_USD", "US", "United States", "New York", "English", "en", "USD", "us"),
    ("UK_GBP", "UK", "United Kingdom", "London", "English", "en", "GBP", "gb"),
    ("DE_BERLIN", "DE", "Germany / DACH", "Berlin", "Deutsch", "de", "EUR", "de"),
    ("ENG_TORONTO", "EN", "Canada / International", "Toronto", "English", "en", "CAD", "ca"),
    ("FR_PARIS", "FR", "France", "Paris", "Francais", "fr", "EUR", "fr"),
    ("SP_BARCELONA", "ES", "Spain / Latin America", "Barcelona", "Espanol", "es", "EUR", "es"),
    ("PT_SAOPAULO", "PT", "Brazil / Portugal", "Sao Paulo", "Portugues", "pt", "BRL", "br"),
    ("RU_STPETERSBURG", "RU", "Russia / CIS", "St. Petersburg", "Russian", "ru", "RUB", "ru"),
    ("AR_DUBAI", "AR", "Middle East / Gulf", "Dubai", "Arabic", "ar", "AED", "ae"),
    ("HI_MUMBAI", "HI", "India / South Asia", "Mumbai", "Hindi", "hi", "INR", "in"),
    ("AU_SYDNEY", "AU", "Australia", "Sydney", "English", "en", "AUD", "au"),
    ("NZ_AUCKLAND", "NZ", "New Zealand", "Auckland", "English", "en", "NZD", "nz"),
    ("IT_ROME", "IT", "Italy", "Rome", "Italiano", "it", "EUR", "it"),
    ("NL_AMSTERDAM", "NL", "Netherlands", "Amsterdam", "Nederlands", "nl", "EUR", "nl"),
    ("PL_WARSAW", "PL", "Poland", "Warsaw", "Polski", "pl", "PLN", "pl"),
    ("CS_PRAGUE", "CS", "Czech Republic", "Prague", "Cestina", "cs", "CZK", "cz"),
    ("HR_ZAGREB", "HR", "Croatia", "Zagreb", "Hrvatski", "hr", "EUR", "hr"),
    ("BG_SOFIA", "BG", "Bulgaria", "Sofia", "Balgarski", "bg", "BGN", "bg"),
    ("RO_BUCHAREST", "RO", "Romania", "Bucharest", "Romana", "ro", "RON", "ro"),
    ("SV_STOCKHOLM", "SV", "Sweden", "Stockholm", "Svenska", "sv", "SEK", "se"),
    ("JA_TOKYO", "JA", "Japan", "Tokyo", "Nihongo", "ja", "JPY", "jp"),
    ("KO_SEOUL", "KO", "South Korea", "Seoul", "Hangugeo", "ko", "KRW", "kr"),
    ("TH_BANGKOK", "TH", "Thailand", "Bangkok", "Thai", "th", "THB", "th"),
    ("VI_HANOI", "VI", "Vietnam", "Hanoi", "Tieng Viet", "vi", "VND", "vn"),
    ("ID_JAKARTA", "ID", "Indonesia", "Jakarta", "Bahasa Indonesia", "id", "IDR", "id"),
    ("MX_MEXICOCITY", "MX", "Mexico", "Mexico City", "Espanol", "es", "MXN", "mx"),
    ("ZA_JOHANNESBURG", "ZA", "South Africa", "Johannesburg", "English", "en", "ZAR", "za"),
    ("NG_LAGOS", "NG", "Nigeria", "Lagos", "English", "en", "NGN", "ng"),
    ("ZH_SHANGHAI", "ZH", "China", "Shanghai", "Chinese", "zh", "CNY", "cn"),
    ("TR_ISTANBUL", "TR", "Turkiye", "Istanbul", "Turkce", "tr", "TRY", "tr"),
)


def _global_variant(row: tuple[str, str, str, str, str, str, str, str]) -> BaseVariant:
    region, xx, market, city, language, lang_code, currency, flag = row
    folder = f"{_GLOBAL_BASE_FOLDER}/{xx}___DDC_CWICR"
    return BaseVariant(
        region=region,
        market=market,
        city=city,
        language=language,
        lang_code=lang_code,
        currency=currency,
        flag=flag,
        positions=_GLOBAL_POSITIONS,
        workitems_path=f"{folder}/{region}_workitems_costs_resources_DDC_CWICR.parquet",
        catalog_folder=folder,
        catalog_token=region,
        bundled=False,
    )


_GLOBAL_FAMILY = BaseFamily(
    key="global",
    name="Russia",
    norm_system="GESN / FER / TER",
    origin="Russia",
    origin_flag="ru",
    description=(
        "One comprehensive work-item catalogue, localized and repriced into 30 "
        "markets and nine languages. Pick your market to get it in your language, "
        "currency and local price level."
    ),
    variants=[_global_variant(r) for r in _GLOBAL_MARKETS],
)


def _national(
    key: str,
    name: str,
    norm_system: str,
    origin: str,
    origin_flag: str,
    description: str,
    *,
    region: str,
    market: str,
    language: str,
    lang_code: str,
    currency: str,
    flag: str,
    positions: int,
    base_folder: str,
    file_token: str,
    catalog_token: str,
    coefficient: bool = False,
    repriceable_markets: int = 0,
) -> BaseFamily:
    """Build a single-home-market national family (bundled, offline-ready)."""
    variant = BaseVariant(
        region=region,
        market=market,
        city="National",
        language=language,
        lang_code=lang_code,
        currency=currency,
        flag=flag,
        positions=positions,
        workitems_path=f"{base_folder}/{file_token}_workitems_costs_resources_DDC_CWICR.parquet",
        catalog_folder=base_folder,
        catalog_token=catalog_token,
        bundled=True,
        coefficient=coefficient,
    )
    return BaseFamily(
        key=key,
        name=name,
        norm_system=norm_system,
        origin=origin,
        origin_flag=origin_flag,
        description=description,
        variants=[variant],
        repriceable_markets=repriceable_markets,
    )


# ── Eight authentic national bases (each bundled, single home market) ────────
# Position counts are the real, deduplicated work-item counts of the bundled
# parquets (verified against the loaded relational store).
_NATIONAL_FAMILIES: tuple[BaseFamily, ...] = (
    _national(
        "china",
        "China (Dinge)",
        "Dinge",
        "China",
        "cn",
        "Authentic Chinese base built from the official Dinge norm system.",
        region="ZH_CHINA",
        market="China",
        language="Chinese",
        lang_code="zh",
        currency="CNY",
        flag="cn",
        positions=10486,
        base_folder="Asia-China-Dinge",
        file_token="ZH_CHINA",
        catalog_token="ZH_CHINA",
        repriceable_markets=49,
    ),
    _national(
        "turkey",
        "Turkiye (Birim Fiyat)",
        "Birim Fiyat",
        "Turkiye",
        "tr",
        "Authentic Turkish base built from the official Birim Fiyat unit-price list.",
        region="TR_NATIONAL",
        market="Turkiye",
        language="Turkce",
        lang_code="tr",
        currency="TRY",
        flag="tr",
        positions=22494,
        base_folder="Europe-Turkey-Birim-Fiyat",
        file_token="TR",
        catalog_token="TR",
        repriceable_markets=49,
    ),
    _national(
        "brazil",
        "Brazil (SINAPI)",
        "SINAPI",
        "Brazil",
        "br",
        "Authentic Brazilian base built from the official SINAPI reference system.",
        region="BR_NATIONAL",
        market="Brazil",
        language="Portugues",
        lang_code="pt",
        currency="BRL",
        flag="br",
        positions=9723,
        base_folder="SouthAmerica-Brazil-SINAPI",
        file_token="BR",
        catalog_token="BR",
        repriceable_markets=49,
    ),
    _national(
        "spain",
        "Spain (BCCA)",
        "BCCA",
        "Spain",
        "es",
        "Authentic Spanish base built from the BCCA construction cost database.",
        region="ES_ANDALUCIA",
        market="Spain (Andalucia)",
        language="Espanol",
        lang_code="es",
        currency="EUR",
        flag="es",
        positions=6453,
        base_folder="Europe-Spain-BCCA",
        file_token="ES_ANDALUCIA",
        catalog_token="ES_ANDALUCIA",
        repriceable_markets=49,
    ),
    _national(
        "italy",
        "Italy (Prezzario Toscana)",
        "Prezzario Regione Toscana",
        "Italy",
        "it",
        "Authentic Italian base built from the Prezzario Regione Toscana.",
        region="IT_TOSCANA",
        market="Italy (Toscana)",
        language="Italiano",
        lang_code="it",
        currency="EUR",
        flag="it",
        positions=5836,
        base_folder="Europe-Italy-Prezzario-Toscana",
        file_token="IT_TOSCANA",
        catalog_token="IT_TOSCANA",
        repriceable_markets=49,
    ),
    _national(
        "greece",
        "Greece (GGDE)",
        "GGDE",
        "Greece",
        "gr",
        "Authentic Greek base built from the official GGDE analytical prices.",
        region="GR_NATIONAL",
        market="Greece",
        language="Ellinika",
        lang_code="el",
        currency="EUR",
        flag="gr",
        positions=2647,
        base_folder="Europe-Greece-GGDE",
        file_token="GR",
        catalog_token="GR",
        repriceable_markets=49,
    ),
    _national(
        "vietnam",
        "Vietnam (Dinh Muc)",
        "Dinh Muc",
        "Vietnam",
        "vn",
        "Authentic Vietnamese coefficient base from the official Dinh Muc norms; "
        "estimable by applying a market resource price sheet.",
        region="VN_NATIONAL",
        market="Vietnam",
        language="Tieng Viet",
        lang_code="vi",
        currency="VND",
        flag="vn",
        positions=4299,
        base_folder="Asia-Vietnam-Dinh-Muc",
        file_token="VN",
        catalog_token="VN",
        coefficient=True,
        repriceable_markets=49,
    ),
    _national(
        "indonesia",
        "Indonesia (AHSP)",
        "AHSP",
        "Indonesia",
        "id",
        "Authentic Indonesian coefficient base from the official AHSP norms; "
        "estimable by applying a market resource price sheet.",
        region="ID_NATIONAL",
        market="Indonesia",
        language="Bahasa Indonesia",
        lang_code="id",
        currency="IDR",
        flag="id",
        positions=2784,
        base_folder="Asia-Indonesia-AHSP",
        file_token="ID",
        catalog_token="ID",
        coefficient=True,
        repriceable_markets=49,
    ),
)

#: All base families, global first, then the national bases largest-first.
BASE_FAMILIES: tuple[BaseFamily, ...] = (_GLOBAL_FAMILY, *_NATIONAL_FAMILIES)


# ── Lookups shared by both routers ──────────────────────────────────────────


def iter_variants() -> list[BaseVariant]:
    """Return every loadable variant across all families (flat list)."""
    return [v for fam in BASE_FAMILIES for v in fam.variants]


_BY_REGION: dict[str, BaseVariant] = {v.region: v for v in iter_variants()}


def variant_by_region(region: str) -> BaseVariant | None:
    """Return the variant for a platform region id, or ``None`` if unknown."""
    return _BY_REGION.get(region)


def github_workitems_files() -> dict[str, str]:
    """Map region id to its work-item parquet path (repo-root relative)."""
    return {v.region: v.workitems_path for v in iter_variants()}


def github_catalog_folder(region: str) -> str | None:
    """Return the repo folder holding a region's resource-catalog CSV."""
    v = _BY_REGION.get(region)
    return v.catalog_folder if v else None


def catalog_token(region: str) -> str | None:
    """Return the token used in ``DDC_CWICR_<token>_Catalog.csv`` for a region."""
    v = _BY_REGION.get(region)
    return v.catalog_token if v else None


def _variant_public(v: BaseVariant, loaded_counts: dict[str, int]) -> dict:
    loaded = loaded_counts.get(v.region, 0)
    return {
        "region": v.region,
        "market": v.market,
        "city": v.city,
        "language": v.language,
        "lang_code": v.lang_code,
        "currency": v.currency,
        "flag": v.flag,
        "positions": v.positions,
        "bundled": v.bundled,
        "coefficient": v.coefficient,
        "loaded": loaded > 10,
        "loaded_positions": loaded,
    }


def public_catalog(loaded_counts: dict[str, int] | None = None) -> dict:
    """Serialize the catalog for the API, merging live loaded counts.

    Args:
        loaded_counts: Region id to the number of currently loaded, active cost
            items, from ``oe_costs_item``. A region with more than 10 loaded
            items is marked ``loaded`` and carries its real count so the browser
            shows the true figure after import rather than only the estimate.

    Returns:
        A JSON-ready dict with a ``families`` list and roll-up totals.
    """
    counts = loaded_counts or {}
    families = []
    for fam in BASE_FAMILIES:
        variants = [_variant_public(v, counts) for v in fam.variants]
        families.append(
            {
                "key": fam.key,
                "name": fam.name,
                "norm_system": fam.norm_system,
                "origin": fam.origin,
                "origin_flag": fam.origin_flag,
                "description": fam.description,
                "market_count": len(fam.variants),
                "repriceable_markets": fam.repriceable_markets,
                # Representative catalogue size: markets in a family share the
                # same work-item count, so the first variant is representative.
                "positions": fam.variants[0].positions if fam.variants else 0,
                "loaded_count": sum(1 for v in variants if v["loaded"]),
                "variants": variants,
            }
        )
    all_variants = iter_variants()
    return {
        "repo": REPO,
        "families": families,
        "total_bases": len(all_variants),
        "total_families": len(BASE_FAMILIES),
        "loaded_regions": sorted(r for r, c in counts.items() if c > 10),
    }
