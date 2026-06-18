# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Built-in estimating-methodology templates (pure data + a pure builder).

This module is the data-driven catalogue of methodology templates the platform
ships with: a neutral international default, core templates for several popular
countries, the Uzbekistan cascading methodology, and a Railway-infrastructure
industry template. The service layer (:mod:`app.modules.methodology.service`)
installs any of these into a project idempotently.

Each template is a plain ``dict`` (see :data:`TEMPLATES`) describing everything
that distinguishes one estimating tradition from another:

* ``slug`` / ``name`` / ``description`` - identity and display text.
* ``country_code`` / ``industry`` - classification (either may be ``None``).
* ``currency`` / ``decimals`` - monetary presentation; the engine never blends
  or converts currencies.
* ``hierarchy_levels`` - the ordered typed levels a BOQ uses under this
  methodology (e.g. section/complex/object/work for railway).
* ``dimensions`` - the analytical dimensions activated, each a flat reference
  list or a value tree (e.g. the CBS "Chapters" / "Главы" tree).
* ``column_preset`` - a named BOQ column preset (GAEB / NRM2 / ...), or ``None``.
* ``base_mapping`` - maps each cascade leaf base token to the resource types
  that feed it (consumed by :func:`app.modules.methodology.bases.resolve_bases`).
* ``composites`` - named sums of leaf base tokens (e.g. SMR = labor + machinery
  + materials).
* ``cascade_steps`` - the ordered markup steps (see
  :func:`app.modules.methodology.cascade.compute_cascade`). Rates and fixed
  amounts are stored as STRINGS so no float ever touches money.
* ``vat_rate`` - convenience copy of the VAT percentage as a string, or ``None``
  when VAT is modelled purely as a cascade step.

Design constraints (mirror cascade.py / bases.py):

* Standard library only - ``decimal``, ``dataclasses`` (via the imported pure
  engine), ``typing``. No ``app.*`` imports except the two sibling PURE engine
  modules, and those are imported lazily inside :func:`build_cascade_spec` /
  re-exported types so this file can still be loaded standalone on Python 3.11
  for unit testing (no SQLAlchemy / Pydantic / FastAPI import is triggered).
* English only; no em-dashes in any string. Money as Decimal-safe strings.

The rates below are sensible, clearly documented defaults, not regulated
figures: a methodology is fully editable in-app once installed, so a user can
adjust every percentage to their jurisdiction and date.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.modules.methodology.cascade import CascadeSpec

__all__ = [
    "TEMPLATES",
    "TEMPLATES_BY_SLUG",
    "INTERNATIONAL_SLUG",
    "list_templates",
    "get_template",
    "build_cascade_spec",
    "build_cascade_spec_from_template",
    "TemplateError",
]

# Slug of the neutral default methodology a project gets when it opts into the
# engine without picking a country. The existing flat international BOQMarkup
# path remains the platform-wide default for projects that never opt in at all.
INTERNATIONAL_SLUG = "international"


class TemplateError(ValueError):
    """Raised when a template cannot be resolved or built into a cascade spec.

    Subclasses :class:`ValueError` so callers catching ``ValueError`` still
    handle it, consistent with ``cascade.CascadeError`` / ``bases``.
    """


# ---------------------------------------------------------------------------
# Reusable building blocks
# ---------------------------------------------------------------------------
#
# The "western flat" tradition: direct cost (labor + materials + equipment +
# subcontract) carries an overhead percentage, then a profit percentage on
# (direct + overhead), then VAT on everything. This is the existing
# international method expressed in the cascade vocabulary so it can coexist as
# a first-class, fully data-driven methodology too.

# Resource-type tokens here are the canonical ones the BOQ resource normaliser
# emits (labor / material / equipment); a country template that needs a finer
# split (e.g. machinery distinct from installed equipment) declares its own
# resource types in base_mapping and the data simply has to use them.
_FLAT_BASE_MAPPING: dict[str, list[str]] = {
    "labor": ["labor"],
    "materials": ["material"],
    "equipment": ["equipment"],
    "subcontract": ["subcontractor"],
}
_FLAT_COMPOSITES: dict[str, list[str]] = {
    "direct": ["labor", "materials", "equipment", "subcontract"],
}


def _flat_steps(
    *, overhead: str, profit: str, vat: str
) -> list[dict[str, Any]]:
    """Build the canonical flat cascade: overhead, profit, then VAT.

    Args:
        overhead: Overhead-and-general-conditions rate, percent, as a string.
        profit: Profit / margin rate, percent, as a string.
        vat: VAT rate, percent, as a string.

    Returns:
        Ordered list of serialized markup-step dicts. Overhead applies to the
        direct-cost composite; profit applies to direct cost plus the overhead
        step; VAT applies to direct cost plus both prior steps.
    """
    return [
        {
            "key": "overhead",
            "label": "Overhead and general conditions",
            "category": "overhead",
            "kind": "percentage",
            "rate": overhead,
            "amount": "0",
            "base": ["direct"],
        },
        {
            "key": "profit",
            "label": "Profit",
            "category": "profit",
            "kind": "percentage",
            "rate": profit,
            "amount": "0",
            "base": ["direct", "overhead"],
        },
        {
            "key": "vat",
            "label": "VAT",
            "category": "tax",
            "kind": "percentage",
            "rate": vat,
            "amount": "0",
            "base": ["direct", "overhead", "profit"],
        },
    ]


# A neutral two-level work breakdown used by the flat templates: a section
# header level and the work line under it. Switchable per methodology.
_FLAT_HIERARCHY: list[dict[str, Any]] = [
    {"key": "section", "label": "Section", "order": 0},
    {"key": "work", "label": "Work", "order": 1},
]

# The customer's 12 standard construction chapters ("Главы строительства" /
# ССР / CBS), seeded as a flat reference list of (code, label) pairs. Modelled
# as a dimension, NOT a hierarchy level, per the locked design. Editable
# in-app, and a pack may replace or extend it.
_CBS_CHAPTERS: list[dict[str, str]] = [
    {"code": "1", "label": "Site preparation"},
    {"code": "2", "label": "Main buildings and structures"},
    {"code": "3", "label": "Auxiliary buildings and structures"},
    {"code": "4", "label": "Energy facilities"},
    {"code": "5", "label": "Transport and communications facilities"},
    {"code": "6", "label": "External networks and utilities"},
    {"code": "7", "label": "Site improvement and landscaping"},
    {"code": "8", "label": "Temporary buildings and structures"},
    {"code": "9", "label": "Other works and costs"},
    {"code": "10", "label": "Maintenance of the developer / client"},
    {"code": "11", "label": "Training of operating personnel"},
    {"code": "12", "label": "Design and survey works"},
]

# Railway typed hierarchy: Section (peregon / station) -> Structure complex ->
# Object -> Work. This is the customer's requested breakdown, switchable.
_RAILWAY_HIERARCHY: list[dict[str, Any]] = [
    {"key": "section", "label": "Section", "order": 0},
    {"key": "complex", "label": "Structure complex", "order": 1},
    {"key": "object", "label": "Object", "order": 2},
    {"key": "work", "label": "Work", "order": 3},
]

# Railway / UZ resource split: construction machinery is part of SMR works,
# while installed equipment is a separate base that carries only some markups.
_CASCADE_BASE_MAPPING: dict[str, list[str]] = {
    "labor": ["labor"],
    "machinery": ["machinery"],
    "materials": ["material"],
    "equipment": ["equipment"],
}
_SMR_COMPOSITE: dict[str, list[str]] = {
    "SMR": ["labor", "machinery", "materials"],
}


def _section_type_dimension() -> dict[str, Any]:
    """Flat section-type reference dimension (extensible per the design)."""
    return {
        "key": "section_type",
        "label": "Section type",
        "kind": "flat",
        "is_required": False,
        "values": [
            {"code": "span", "label": "Span (peregon)"},
            {"code": "station", "label": "Station"},
            {"code": "junction", "label": "Junction"},
            {"code": "other", "label": "Other"},
        ],
    }


def _stage_dimension() -> dict[str, Any]:
    """Flat stage reference dimension (design / construction phases)."""
    return {
        "key": "stage",
        "label": "Stage",
        "kind": "flat",
        "is_required": False,
        "values": [
            {"code": "design", "label": "Design"},
            {"code": "procurement", "label": "Procurement"},
            {"code": "construction", "label": "Construction"},
            {"code": "commissioning", "label": "Commissioning"},
        ],
    }


def _cbs_dimension() -> dict[str, Any]:
    """The CBS "Chapters" dimension seeded from the 12 standard chapters."""
    return {
        "key": "cbs_chapter",
        "label": "Construction chapter (CBS)",
        "kind": "tree",
        "is_required": False,
        "values": [dict(ch) for ch in _CBS_CHAPTERS],
    }


# ---------------------------------------------------------------------------
# The template catalogue
# ---------------------------------------------------------------------------
#
# Country VAT rates and typical overhead/profit are documented defaults. They
# are intentionally round, clearly-labelled starting points, fully editable
# once installed - never presented as official regulated figures.

_INTERNATIONAL_TEMPLATE: dict[str, Any] = {
    "slug": INTERNATIONAL_SLUG,
    "name": "International (neutral)",
    "description": (
        "Neutral flat methodology: direct cost, then overhead, profit and VAT. "
        "A sensible default for any country before a local template is chosen."
    ),
    "country_code": None,
    "industry": None,
    "currency": "",
    "decimals": 2,
    "hierarchy_levels": _FLAT_HIERARCHY,
    "dimensions": [_stage_dimension()],
    "column_preset": None,
    "base_mapping": _FLAT_BASE_MAPPING,
    "composites": _FLAT_COMPOSITES,
    "cascade_steps": _flat_steps(overhead="12", profit="8", vat="0"),
    "vat_rate": "0",
}

# Seven popular countries, migrated from the hardcoded DEFAULT_MARKUP_TEMPLATES
# tradition into data. Each is the flat method with country-typical defaults.
_COUNTRY_TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": "germany",
        "name": "Germany",
        "description": "German flat estimate with BGK overhead, profit and VAT.",
        "country_code": "DE",
        "industry": None,
        "currency": "EUR",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": "GAEB",
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="13", profit="6", vat="19"),
        "vat_rate": "19",
    },
    {
        "slug": "united_kingdom",
        "name": "United Kingdom",
        "description": "UK flat estimate with preliminaries, OHP and VAT.",
        "country_code": "GB",
        "industry": None,
        "currency": "GBP",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": "NRM2",
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="12", profit="6", vat="20"),
        "vat_rate": "20",
    },
    {
        "slug": "united_states",
        "name": "United States",
        "description": (
            "US flat estimate with general conditions, overhead and profit. "
            "Sales tax varies by state, so the tax step defaults to zero."
        ),
        "country_code": "US",
        "industry": None,
        "currency": "USD",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": "CSI",
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="10", profit="10", vat="0"),
        "vat_rate": "0",
    },
    {
        "slug": "france",
        "name": "France",
        "description": "French flat estimate with site overhead, profit and TVA.",
        "country_code": "FR",
        "industry": None,
        "currency": "EUR",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": None,
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="12", profit="7", vat="20"),
        "vat_rate": "20",
    },
    {
        "slug": "united_arab_emirates",
        "name": "United Arab Emirates",
        "description": "UAE flat estimate with preliminaries, profit and VAT.",
        "country_code": "AE",
        "industry": None,
        "currency": "AED",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": None,
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="12", profit="8", vat="5"),
        "vat_rate": "5",
    },
    {
        "slug": "india",
        "name": "India",
        "description": "Indian flat estimate with overhead, profit and GST.",
        "country_code": "IN",
        "industry": None,
        "currency": "INR",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": None,
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="10", profit="10", vat="18"),
        "vat_rate": "18",
    },
    {
        "slug": "australia",
        "name": "Australia",
        "description": "Australian flat estimate with preliminaries, margin and GST.",
        "country_code": "AU",
        "industry": None,
        "currency": "AUD",
        "decimals": 2,
        "hierarchy_levels": _FLAT_HIERARCHY,
        "dimensions": [_stage_dimension()],
        "column_preset": None,
        "base_mapping": _FLAT_BASE_MAPPING,
        "composites": _FLAT_COMPOSITES,
        "cascade_steps": _flat_steps(overhead="12", profit="8", vat="10"),
        "vat_rate": "10",
    },
]

# The Uzbekistan cascading methodology - the canonical reference cascade from
# the design doc (section 5). SMR = labor + machinery + materials; installed
# equipment is a separate base that skips the SMR-only winter/contractor steps
# but still carries insurance, contingency and VAT.
#
# The first two steps default to zero rate so the cascade is correct out of the
# box (those rates are project-specific seasonal / contractual figures the user
# fills in); insurance (0.32 percent) and VAT (12 percent) are the stable,
# well-known figures.
_UZBEKISTAN_TEMPLATE: dict[str, Any] = {
    "slug": "uzbekistan",
    "name": "Uzbekistan (cascading)",
    "description": (
        "Uzbekistan cascading methodology. SMR (labor, machinery, materials) "
        "and installed equipment are distinct bases; markups cascade through "
        "temporary/winter, contractor, insurance, contingency and VAT."
    ),
    "country_code": "UZ",
    "industry": None,
    "currency": "UZS",
    "decimals": 2,
    "hierarchy_levels": _RAILWAY_HIERARCHY,
    "dimensions": [
        _cbs_dimension(),
        _section_type_dimension(),
        _stage_dimension(),
    ],
    "column_preset": None,
    "base_mapping": _CASCADE_BASE_MAPPING,
    "composites": _SMR_COMPOSITE,
    "cascade_steps": [
        {
            "key": "other_temp_winter",
            "label": "Temporary buildings and winter works",
            "category": "temp_winter",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": ["SMR"],
        },
        {
            "key": "contractor_other",
            "label": "Other contractor costs",
            "category": "contractor_other",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": ["SMR", "other_temp_winter"],
        },
        {
            "key": "insurance",
            "label": "Insurance",
            "category": "insurance",
            "kind": "percentage",
            "rate": "0.32",
            "amount": "0",
            "base": ["SMR", "equipment", "other_temp_winter", "contractor_other"],
        },
        {
            "key": "contingency",
            "label": "Contingency reserve",
            "category": "contingency",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": [
                "SMR",
                "equipment",
                "other_temp_winter",
                "contractor_other",
                "insurance",
            ],
        },
        {
            "key": "vat",
            "label": "VAT",
            "category": "tax",
            "kind": "percentage",
            "rate": "12",
            "amount": "0",
            "base": [
                "SMR",
                "equipment",
                "other_temp_winter",
                "contractor_other",
                "insurance",
                "contingency",
            ],
        },
    ],
    "vat_rate": "12",
}

# Railway-infrastructure industry template. Country-neutral (currency blank,
# VAT a placeholder step) but ships the full railway typed hierarchy plus the
# CBS / section-type / stage dimensions and the SMR-vs-equipment cascade, so an
# infrastructure estimator gets the right structure regardless of country.
_RAILWAY_TEMPLATE: dict[str, Any] = {
    "slug": "railway_infrastructure",
    "name": "Railway infrastructure",
    "description": (
        "Railway-infrastructure industry methodology: Section, Structure "
        "complex, Object and Work levels; CBS chapters, section-type and "
        "stage dimensions; SMR and installed-equipment cascade."
    ),
    "country_code": None,
    "industry": "railway",
    "currency": "",
    "decimals": 2,
    "hierarchy_levels": _RAILWAY_HIERARCHY,
    "dimensions": [
        _cbs_dimension(),
        _section_type_dimension(),
        _stage_dimension(),
    ],
    "column_preset": None,
    "base_mapping": _CASCADE_BASE_MAPPING,
    "composites": _SMR_COMPOSITE,
    "cascade_steps": [
        {
            "key": "other_temp_winter",
            "label": "Temporary buildings and winter works",
            "category": "temp_winter",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": ["SMR"],
        },
        {
            "key": "contractor_other",
            "label": "Other contractor costs",
            "category": "contractor_other",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": ["SMR", "other_temp_winter"],
        },
        {
            "key": "contingency",
            "label": "Contingency reserve",
            "category": "contingency",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": ["SMR", "equipment", "other_temp_winter", "contractor_other"],
        },
        {
            "key": "vat",
            "label": "VAT",
            "category": "tax",
            "kind": "percentage",
            "rate": "0",
            "amount": "0",
            "base": [
                "SMR",
                "equipment",
                "other_temp_winter",
                "contractor_other",
                "contingency",
            ],
        },
    ],
    "vat_rate": None,
}


# Ordered catalogue: international first, then countries, then UZ, then railway.
TEMPLATES: tuple[dict[str, Any], ...] = (
    _INTERNATIONAL_TEMPLATE,
    *_COUNTRY_TEMPLATES,
    _UZBEKISTAN_TEMPLATE,
    _RAILWAY_TEMPLATE,
)

# Index by slug for O(1) lookup. Built once at import time.
TEMPLATES_BY_SLUG: dict[str, dict[str, Any]] = {t["slug"]: t for t in TEMPLATES}


def list_templates() -> list[dict[str, Any]]:
    """Return all built-in templates, in catalogue order.

    The returned dicts are the live catalogue objects; callers that mutate
    them would corrupt the catalogue, so the service layer copies before
    persisting. (They are not deep-copied here to keep this helper allocation
    free for the common read-only listing path.)
    """
    return list(TEMPLATES)


def get_template(slug: str) -> dict[str, Any]:
    """Return the template with ``slug`` or raise :class:`TemplateError`."""
    try:
        return TEMPLATES_BY_SLUG[slug]
    except KeyError as exc:
        raise TemplateError(f"unknown methodology template {slug!r}") from exc


def build_cascade_spec(
    *,
    slug: str,
    currency: str,
    decimals: int,
    composites: Mapping[str, Any],
    cascade_steps: Any,
) -> CascadeSpec:
    """Build a :class:`CascadeSpec` from serialized methodology fields.

    This is the single bridge from the persisted / template representation
    (composites as ``{name: [tokens]}`` and steps as a list of dicts with
    string rates/amounts) to the frozen-dataclass spec the pure cascade engine
    consumes. It is deliberately permissive about input numeric types (str /
    int / Decimal) because the same builder serves both the JSON-backed ORM row
    and the in-memory template dict; the engine itself does the strict Decimal
    coercion and all structural validation.

    Args:
        slug: Methodology slug (informational on the spec).
        currency: ISO currency code (informational; never used to convert).
        decimals: Rounding precision passed straight to the engine.
        composites: Mapping of composite name to a sequence of leaf base
            tokens, e.g. ``{"SMR": ["labor", "machinery", "materials"]}``.
        cascade_steps: Iterable of step dicts, each with ``key``, ``label``,
            ``category``, ``kind`` and either ``rate`` (percentage) or
            ``amount`` (fixed), plus a ``base`` list of tokens.

    Returns:
        A :class:`CascadeSpec` ready for ``compute_cascade``.

    Raises:
        TemplateError: If a step is not a mapping or is missing a required key,
            or if a composite member list is malformed.
    """
    # Imported lazily so a standalone (Python 3.11) import of this module for
    # the template-data unit tests does not pull the cascade module until a
    # spec is actually built (and even then cascade.py is itself stdlib-only).
    from decimal import Decimal

    from app.modules.methodology.cascade import CascadeSpec, MarkupStep

    if not isinstance(composites, Mapping):
        raise TemplateError(
            f"composites must be a mapping, got {type(composites).__name__}"
        )

    composites_built: dict[str, tuple[str, ...]] = {}
    for name, members in composites.items():
        if isinstance(members, str) or not _is_sequence(members):
            raise TemplateError(
                f"composite {name!r} must map to a list of base tokens, "
                f"got {type(members).__name__}"
            )
        composites_built[str(name)] = tuple(str(m) for m in members)

    steps_built: list[MarkupStep] = []
    for raw in cascade_steps or ():
        if not isinstance(raw, Mapping):
            raise TemplateError(
                f"each cascade step must be a mapping, got {type(raw).__name__}"
            )
        try:
            key = str(raw["key"])
            kind = str(raw["kind"])
        except KeyError as exc:
            raise TemplateError(
                f"cascade step is missing required field {exc.args[0]!r}"
            ) from exc

        base_raw = raw.get("base", ())
        if isinstance(base_raw, str) or not _is_sequence(base_raw):
            raise TemplateError(
                f"cascade step {key!r} base must be a list of tokens, "
                f"got {type(base_raw).__name__}"
            )

        steps_built.append(
            MarkupStep(
                key=key,
                label=str(raw.get("label", key)),
                category=str(raw.get("category", "other")),
                kind=kind,
                # Decimal() accepts str / int directly; the engine re-validates.
                rate=Decimal(str(raw.get("rate", "0") or "0")),
                amount=Decimal(str(raw.get("amount", "0") or "0")),
                base=tuple(str(token) for token in base_raw),
            )
        )

    return CascadeSpec(
        slug=slug,
        currency=currency,
        decimals=int(decimals),
        composites=composites_built,
        steps=tuple(steps_built),
    )


def build_cascade_spec_from_template(slug: str) -> CascadeSpec:
    """Resolve a built-in template by slug and build its cascade spec."""
    tpl = get_template(slug)
    return build_cascade_spec(
        slug=tpl["slug"],
        currency=tpl["currency"],
        decimals=tpl["decimals"],
        composites=tpl["composites"],
        cascade_steps=tpl["cascade_steps"],
    )


def _is_sequence(value: object) -> bool:
    """True for a list / tuple (the only sequence shapes templates use).

    A bare ``str`` is intentionally excluded by callers before this is reached;
    this helper just rejects non-iterables / mappings so a malformed template
    field fails loudly instead of iterating characters or dict keys.
    """
    return isinstance(value, (list, tuple))
