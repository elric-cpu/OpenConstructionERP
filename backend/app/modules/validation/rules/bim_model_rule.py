# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BIMModelRule - model-level validation rules for BIM models.

A :class:`BIMModelRule` sees ALL of a model's elements at once, which the
per-element :class:`app.modules.validation.rules.bim_element_rule.BIMElementRule`
cannot: duplicate identifiers, whole-category gaps, unit consistency and
georeference sanity are only visible across the full element set.

The shape deliberately mirrors the per-element rule so the driving service
(:mod:`app.modules.validation.bim_validation_service`) can fold both families
into one :class:`~app.modules.validation.models.ValidationReport` with identical
counting semantics:

* :meth:`BIMModelRule.applies` is the model-level analogue of
  ``BIMElementRule.matches`` - it decides whether the rule contributes a check
  at all (an inapplicable rule adds nothing, exactly like a per-element rule
  whose filter matched no element). It defaults to "applies when the model has
  at least one element", so a genuinely empty model still scores as *skipped*
  rather than being flooded with "everything is missing" findings.
* :meth:`BIMModelRule.evaluate` returns only FAILING
  :class:`BIMModelRuleResult` rows (an empty list means the check passed),
  mirroring ``BIMElementRule.evaluate``.

Rules are stateless singletons collected in :data:`BIM_MODEL_RULES`. Every rule
degrades gracefully on sparse or malformed data - it must never raise on a
model with missing metadata, blank ids or odd property shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.modules.validation.rules.bim_element_rule import (
    Severity,
    _coerce_number,
    _has_value,
    _normalized_category,
)

# Coordinates whose absolute value exceeds this (metres) are implausible for a
# real site placement - roughly 10 000 km, well beyond any earthly coordinate.
MAX_PLAUSIBLE_COORD_M = 1e7
# Below this magnitude a coordinate counts as "zero" (origin placement).
_ZERO_EPS = 1e-9
# How many colliding element ids / coordinates to keep in a finding's details.
_DETAIL_CAP = 50

# Expected element categories a reasonably complete building model should carry.
# Each entry is ``(human label, (element-type prefixes,))``; a category counts
# as present when any element's ifc-stripped type starts with one of its
# prefixes.
DEFAULT_EXPECTED_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("walls", ("wall",)),
    ("slabs or floors", ("slab", "floor")),
    ("columns or beams", ("column", "beam")),
    ("doors", ("door",)),
    ("windows", ("window",)),
    ("spaces", ("space", "room", "zone")),
)

# Metadata keys that indicate the model carries georeference / placement info.
_GEOREF_KEYS: tuple[str, ...] = (
    "georeference",
    "geo_reference",
    "coordinate_system",
    "coordinatesystem",
    "crs",
    "epsg",
    "base_point",
    "project_base_point",
    "survey_point",
    "site_placement",
    "placement",
    "location",
    "map_conversion",
    "site",
    "latitude",
    "longitude",
    "northing",
    "easting",
)

# Element/property keys under which a per-element unit system may be declared.
_UNIT_PROPERTY_KEYS: tuple[str, ...] = ("unit_system", "units", "unit")


# ── Result + context shapes ──────────────────────────────────────────────────


@dataclass
class BIMModelRuleResult:
    """Single model-level finding, shaped like the per-element result so the
    service can serialise both with one code path.
    """

    rule_id: str
    rule_name: str
    severity: Severity
    passed: bool
    message: str
    element_ref: str | None = None
    element_id: str | None = None
    element_name: str | None = None
    element_type: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class BIMModelContext:
    """Model-level facts a :class:`BIMModelRule` reasons over.

    Built from a ``BIMModel`` ORM row via :meth:`from_model`, but every field
    is plain data so the rules stay unit-testable with a hand-built context.
    """

    model_id: str | None = None
    model_name: str | None = None
    unit_system: str | None = None
    had_unit_assignment: bool | None = None
    units_declared: bool = False
    georeference: dict[str, Any] | None = None
    bounding_box: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    expected_categories: tuple[tuple[str, tuple[str, ...]], ...] = DEFAULT_EXPECTED_CATEGORIES

    @classmethod
    def from_model(cls, model: Any) -> BIMModelContext:
        """Project a ``BIMModel`` ORM row onto a context. Fail-soft throughout:
        a model with no metadata yields an all-empty context, never an error.
        """
        meta = _as_dict(getattr(model, "metadata_", None))
        unit_system, had_assignment, units_declared = _read_units(meta.get("units"), meta)
        bbox = getattr(model, "bounding_box", None)
        return cls(
            model_id=_str_or_none(getattr(model, "id", None)),
            model_name=getattr(model, "name", None),
            unit_system=unit_system,
            had_unit_assignment=had_assignment,
            units_declared=units_declared,
            georeference=_read_georeference(meta),
            bounding_box=bbox if isinstance(bbox, dict) else None,
            metadata=meta,
        )


# ── Base class ───────────────────────────────────────────────────────────────


class BIMModelRule(ABC):
    """Base class for model-level BIM validation rules."""

    rule_id: str = ""
    name: str = ""
    severity: Severity = "warning"
    description: str = ""

    def applies(self, elements: list[Any], context: BIMModelContext) -> bool:  # noqa: ARG002
        """Return True when the rule should contribute a check for this model.

        Defaults to "there is at least one element". Rules that need a specific
        signal (e.g. unit consistency needs some unit information) override this
        so an absent signal skips the check instead of failing it.
        """
        return len(elements) > 0

    @abstractmethod
    def evaluate(self, elements: list[Any], context: BIMModelContext) -> list[BIMModelRuleResult]:
        """Return failing results (empty list == the check passed)."""
        ...

    def _fail(
        self,
        message: str,
        *,
        element_ref: str | None = None,
        element_name: str | None = None,
        element_type: str | None = None,
        details: dict[str, Any] | None = None,
        severity: Severity | None = None,
    ) -> BIMModelRuleResult:
        """Build a failing :class:`BIMModelRuleResult` for this rule."""
        return BIMModelRuleResult(
            rule_id=self.rule_id,
            rule_name=self.name,
            severity=severity or self.severity,
            passed=False,
            message=message,
            element_ref=element_ref,
            element_id=element_ref,
            element_name=element_name,
            element_type=element_type,
            details=details or {},
        )


# ── Rules ────────────────────────────────────────────────────────────────────


class DuplicateIdentifierRule(BIMModelRule):
    """Flag identifiers shared by more than one element."""

    rule_id = "bim.model.duplicate_identifier"
    name = "Element identifiers must be unique"
    severity = "error"
    description = (
        "Two or more elements share the same stable id / GUID. Duplicate "
        "identifiers break element references, BOQ links and round-trips, and "
        "usually mean a broken export or a merge of two models. Each duplicated "
        "id is reported once with the colliding elements."
    )

    def evaluate(self, elements: list[Any], context: BIMModelContext) -> list[BIMModelRuleResult]:
        by_id: dict[str, list[str]] = defaultdict(list)
        for elem in elements:
            sid = _element_stable_id(elem)
            if sid:
                by_id[sid].append(_element_primary_id(elem))

        results: list[BIMModelRuleResult] = []
        for sid, members in by_id.items():
            if len(members) > 1:
                results.append(
                    self._fail(
                        f"Identifier '{sid}' is shared by {len(members)} elements; identifiers must be unique",
                        element_ref=sid,
                        details={
                            "stable_id": sid,
                            "count": len(members),
                            "element_ids": members[:_DETAIL_CAP],
                        },
                    )
                )
        return results


class ModelCompletenessRule(BIMModelRule):
    """Flag any expected element category that has zero elements."""

    rule_id = "bim.model.expected_categories_present"
    name = "Model should contain every expected element category"
    severity = "warning"
    description = (
        "Compares the model against a checklist of expected categories (walls, "
        "slabs/floors, columns/beams, doors, windows, spaces). A category with "
        "no elements at all is flagged as a potential scope gap - the discipline "
        "may be missing or not yet modelled."
    )

    def evaluate(self, elements: list[Any], context: BIMModelContext) -> list[BIMModelRuleResult]:
        expected = context.expected_categories or DEFAULT_EXPECTED_CATEGORIES
        present_norms = {_normalized_category(e) for e in elements}
        present_norms.discard("")

        results: list[BIMModelRuleResult] = []
        for label, prefixes in expected:
            if not any(norm.startswith(p) for norm in present_norms for p in prefixes):
                results.append(
                    self._fail(
                        f"No {label} found in the model; this expected category may be missing",
                        details={"missing_category": label, "prefixes": list(prefixes)},
                    )
                )
        return results


class UnitConsistencyRule(BIMModelRule):
    """Flag mixed or missing/uncertain unit declarations."""

    rule_id = "bim.model.unit_consistency"
    name = "Model units must be declared and consistent"
    severity = "warning"
    description = (
        "Checks that the model declares a single, reliable unit system. More "
        "than one system across the model or its elements is flagged as mixed; "
        "a missing or uncertain declaration is flagged so quantities are not "
        "trusted blindly. Fail-soft: a model with no unit information at all is "
        "skipped, not failed."
    )

    def applies(self, elements: list[Any], context: BIMModelContext) -> bool:
        if not elements:
            return False
        # Only run when there is SOME unit information to reason about; a model
        # carrying no unit indication at all is skipped (fail-soft).
        return context.units_declared or bool(_element_unit_systems(elements))

    def evaluate(self, elements: list[Any], context: BIMModelContext) -> list[BIMModelRuleResult]:
        systems: set[str] = set()
        if context.unit_system and context.unit_system not in {"unknown", "mixed"}:
            systems.add(context.unit_system)
        systems |= _element_unit_systems(elements)

        # Explicit "mixed", or two or more distinct systems declared anywhere.
        if context.unit_system == "mixed" or len(systems) > 1:
            declared = sorted(systems) or ["mixed"]
            return [
                self._fail(
                    "Model mixes more than one unit system (" + ", ".join(declared) + "); use one consistent system",
                    details={"declared_systems": declared},
                )
            ]

        # Present but unreliable: no unit assignment, or an unknown/blank system.
        if context.had_unit_assignment is False or context.unit_system in {None, "", "unknown"}:
            return [
                self._fail(
                    "Model has no reliable unit declaration; quantities are assumed to be in SI metres - "
                    "confirm the source units",
                    details={
                        "unit_system": context.unit_system,
                        "had_assignment": context.had_unit_assignment,
                    },
                )
            ]
        return []


class GeoreferenceSanityRule(BIMModelRule):
    """Flag a missing georeference or an implausible placement."""

    rule_id = "bim.model.georeference"
    name = "Model should carry a plausible georeference"
    severity = "info"
    description = (
        "Flags when the model carries no coordinate / placement / georeference "
        "information, or when the placement looks wrong (sitting exactly at the "
        "origin, or with absurdly large coordinates that hint at a wrong survey "
        "point or unit). Informational and fail-soft: absent data yields a "
        "suggestion, never an error."
    )

    def evaluate(self, elements: list[Any], context: BIMModelContext) -> list[BIMModelRuleResult]:
        results: list[BIMModelRuleResult] = []
        if not context.georeference:
            results.append(
                self._fail(
                    "Model carries no georeference (coordinate system / base point / survey point); "
                    "disciplines cannot be coordinated on a shared real-world location",
                    details={"reason": "no_georeference"},
                )
            )

        coords = _collect_coordinates(context)
        if coords:
            if all(abs(c) < _ZERO_EPS for c in coords):
                results.append(
                    self._fail(
                        "Model placement is at the origin (0, 0, 0); it may not be georeferenced",
                        details={"reason": "origin_placement", "coordinates": _round_coords(coords)},
                    )
                )
            else:
                huge = [c for c in coords if abs(c) > MAX_PLAUSIBLE_COORD_M]
                if huge:
                    results.append(
                        self._fail(
                            "Model placement coordinates are implausibly large; the survey point or units may be wrong",
                            details={"reason": "implausible_coordinates", "coordinates": _round_coords(huge)},
                        )
                    )
        return results


# ── Registry ─────────────────────────────────────────────────────────────────

BIM_MODEL_RULES: list[BIMModelRule] = [
    DuplicateIdentifierRule(),
    ModelCompletenessRule(),
    UnitConsistencyRule(),
    GeoreferenceSanityRule(),
]
"""Ordered list of enabled model-level BIM rules."""


def get_model_rules_by_ids(rule_ids: list[str] | None) -> list[BIMModelRule]:
    """Return the subset of :data:`BIM_MODEL_RULES` matching ``rule_ids``.

    ``None`` / empty returns the full set (default full run). Unknown ids are
    silently skipped, mirroring
    :func:`app.modules.validation.rules.bim_universal.get_rules_by_ids`.
    """
    if not rule_ids:
        return list(BIM_MODEL_RULES)
    wanted = set(rule_ids)
    return [r for r in BIM_MODEL_RULES if r.rule_id in wanted]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _read_units(units_block: Any, meta: dict[str, Any]) -> tuple[str | None, bool | None, bool]:
    """Resolve ``(unit_system, had_assignment, declared)`` from model metadata.

    ``units_block`` is ``metadata['units']`` - a dict (the resolved unit
    metadata), a bare string, or absent. Falls back to flat unit keys on the
    metadata. Fail-soft: unknown shapes yield ``(None, None, False)``.
    """
    if isinstance(units_block, dict):
        us = units_block.get("unit_system")
        unit_system = str(us).strip().lower() if _has_text(us) else None
        ha = units_block.get("had_assignment")
        had_assignment = ha if isinstance(ha, bool) else None
        return unit_system, had_assignment, True
    if _has_text(units_block):
        return str(units_block).strip().lower(), None, True
    for key in _UNIT_PROPERTY_KEYS:
        val = meta.get(key)
        if _has_text(val):
            return str(val).strip().lower(), None, True
    return None, None, False


def _read_georeference(meta: dict[str, Any]) -> dict[str, Any] | None:
    """Return the georeference-bearing subset of ``meta`` (or ``None``)."""
    found = {k: meta[k] for k in _GEOREF_KEYS if k in meta and _has_value(meta[k])}
    return found or None


def _element_unit_systems(elements: list[Any]) -> set[str]:
    """Distinct per-element unit-system declarations across the model."""
    out: set[str] = set()
    for elem in elements:
        props = getattr(elem, "properties", None) or {}
        if not isinstance(props, dict):
            continue
        for key in _UNIT_PROPERTY_KEYS:
            val = props.get(key)
            if _has_text(val):
                out.add(str(val).strip().lower())
    return out


def _element_stable_id(elem: Any) -> str | None:
    """Best-effort GUID / stable id used to detect duplicates."""
    sid = getattr(elem, "stable_id", None)
    if _has_text(sid):
        return str(sid).strip()
    props = getattr(elem, "properties", None) or {}
    if isinstance(props, dict):
        for key in ("guid", "global_id", "globalid", "ifc_guid"):
            val = props.get(key)
            if _has_text(val):
                return str(val).strip()
    return None


def _element_primary_id(elem: Any) -> str:
    """Primary id for listing which elements collided on a duplicate."""
    for attr in ("id", "stable_id"):
        val = getattr(elem, attr, None)
        if val is not None and str(val).strip():
            return str(val)
    return ""


def _collect_coordinates(context: BIMModelContext, *, depth_cap: int = 5) -> list[float]:
    """Gather numeric coordinates from georeference points and the bounding box.

    Used for the plausibility checks (origin / absurdly large). Fail-soft:
    anything that is not a number is ignored, never raised on.
    """
    coords: list[float] = []
    georef = context.georeference
    if isinstance(georef, dict):
        for key in ("base_point", "project_base_point", "survey_point", "placement", "location"):
            coords.extend(_extract_numbers(georef.get(key), depth_cap))
        for key in ("latitude", "longitude", "northing", "easting", "x", "y", "z"):
            num = _coerce_number(georef.get(key))
            if num is not None:
                coords.append(num)
    coords.extend(_extract_numbers(context.bounding_box, depth_cap))
    return coords


def _extract_numbers(obj: Any, depth_cap: int) -> list[float]:
    """Recursively pull numbers out of a coordinate-ish list/dict. Bounded depth
    and isinstance-guarded, so it cannot raise on odd shapes.
    """
    if depth_cap <= 0:
        return []
    out: list[float] = []
    if isinstance(obj, (list, tuple)):
        for item in obj:
            out.extend(_extract_numbers(item, depth_cap - 1))
    elif isinstance(obj, dict):
        for key in ("x", "y", "z", "min", "max", "point", "origin", "elevation", "lat", "lon"):
            if key in obj:
                out.extend(_extract_numbers(obj[key], depth_cap - 1))
    else:
        num = _coerce_number(obj)
        if num is not None:
            out.append(num)
    return out


def _round_coords(coords: list[float]) -> list[float]:
    """Round + cap a coordinate list for a compact finding payload."""
    return [round(c, 4) for c in coords[:_DETAIL_CAP]]
