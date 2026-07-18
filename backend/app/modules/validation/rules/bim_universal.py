# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Universal per-element BIM validation rules.

This module declares a small library of :class:`BIMElementRule` instances
that apply to any BIM/IFC model regardless of jurisdiction. They are the
"boq_quality" equivalent for BIM element data.

Rules declared here:

* ``bim.wall.has_thickness`` - every Wall must have a thickness > 0
* ``bim.structural.has_material`` - every Structural* element must declare
  a ``material`` property
* ``bim.wall.has_fire_rating`` - every Wall should have ``fire_rating``
  (warning, not error)
* ``bim.door.has_dimensions`` - every Door must have both width and height
* ``bim.window.has_dimensions`` - every Window must have both width and
  height
* ``bim.mep.has_system`` - MEP elements must declare ``system`` or
  ``system_type``
* ``bim.element.has_storey`` - every element should have ``storey``
  populated (warning)
* ``bim.element.name_not_none`` - every element must have a meaningful
  name (warning)
* ``bim.category.required_property`` - data-driven per-category completeness:
  each category must expose at least one required property (warning)
* ``bim.element.has_classification`` - every element should carry a
  classification code (warning)
* ``bim.asset.has_type_identifier`` - asset-relevant elements should carry a
  type/model identifier (info)
* ``bim.asset.has_mark_tag`` - asset-relevant elements should carry a
  mark/tag (info)
* ``bim.space.identity`` - spaces need a name, a number and a positive
  area (warning)
* ``bim.hosted.has_host`` - hosted elements (doors, windows) must reference a
  host/parent (warning)
* ``bim.door.min_clear_width`` - a declared door width must meet the minimum
  clear width (warning)
* ``bim.quantity.non_negative`` - dimensional quantities (areas, volumes,
  lengths, counts) must not be negative (error)
* ``bim.mep.has_size`` - distribution elements (ducts, pipes, trays, conduits)
  should declare a size or diameter (warning)
* ``bim.circulation.has_dimensions`` - stairs and ramps should declare a width
  for egress and accessibility (warning)
* ``bim.element.has_type_name`` - physical build elements should name their
  type/family so they roll up in type schedules (info)
* ``bim.element.has_phase`` - every element should declare a phase/status so
  4D phasing and renovation scope work (info)

Usage::

    from app.modules.validation.rules.bim_universal import BIM_UNIVERSAL_RULES

    for rule in BIM_UNIVERSAL_RULES:
        ...

The list is considered immutable at import time - do NOT mutate it from
callers. Instead, filter it:
``[r for r in BIM_UNIVERSAL_RULES if r.rule_id in requested]``.
"""

from __future__ import annotations

from app.modules.validation.rules.bim_element_rule import BIMElementRule

# ── Rule definitions ─────────────────────────────────────────────────────────

WALL_HAS_THICKNESS = BIMElementRule(
    rule_id="bim.wall.has_thickness",
    name="Wall elements must have thickness > 0",
    severity="error",
    description=(
        "Every wall element must expose a positive thickness in its "
        "quantities (thickness_m or thickness). Walls without thickness "
        "cannot be used for takeoff or costing."
    ),
    element_filter={"element_type_startswith": ["wall", "ifcwall"]},
    # MUST be a number > 0 - a presence-only check let thickness_m=0 (or the
    # non-numeric string "0,24") pass and defeated the takeoff/costing
    # guarantee the rule name makes (E-BIM-010).
    require_any_positive_quantity=["thickness_m", "thickness", "width_m", "width"],
)

STRUCTURAL_HAS_MATERIAL = BIMElementRule(
    rule_id="bim.structural.has_material",
    name="Structural elements must declare a material",
    severity="error",
    description=(
        "Every element whose type starts with 'Structural' (or the IFC "
        "equivalent) must carry a 'material' property so material "
        "takeoffs and LCA reports can be produced."
    ),
    element_filter={
        "element_type_startswith": [
            "structural",
            "ifcbeam",
            "ifccolumn",
            "ifcfooting",
            "ifcslab",
            "ifcmember",
            "ifcpile",
        ],
    },
    property_checks=[{"property": "material", "must_exist": True}],
)

WALL_HAS_FIRE_RATING = BIMElementRule(
    rule_id="bim.wall.has_fire_rating",
    name="Wall elements should have a fire_rating property",
    severity="warning",
    description=(
        "Walls without a 'fire_rating' property cannot be validated "
        "against fire-compartment design requirements. Treated as a "
        "warning - many temporary or non-compartmenting walls are exempt."
    ),
    element_filter={"element_type_startswith": ["wall", "ifcwall"]},
    property_checks=[{"property": "fire_rating", "must_exist": True}],
)

DOOR_HAS_DIMENSIONS = BIMElementRule(
    rule_id="bim.door.has_dimensions",
    name="Door elements must have width and height",
    severity="error",
    description=("Every door must declare both width and height in either its properties or its quantities dict."),
    element_filter={"element_type_startswith": ["door", "ifcdoor"]},
    require_any_of_properties=["width", "width_m", "overall_width"],
    # Dimensions must be positive numbers, not merely present (E-BIM-010).
    require_any_positive_quantity=["width", "width_m", "height", "height_m"],
)

WINDOW_HAS_DIMENSIONS = BIMElementRule(
    rule_id="bim.window.has_dimensions",
    name="Window elements must have width and height",
    severity="error",
    description=("Every window must declare both width and height in either its properties or its quantities dict."),
    element_filter={"element_type_startswith": ["window", "ifcwindow"]},
    require_any_of_properties=["width", "width_m", "overall_width"],
    # Dimensions must be positive numbers, not merely present (E-BIM-010).
    require_any_positive_quantity=["width", "width_m", "height", "height_m"],
)

MEP_HAS_SYSTEM = BIMElementRule(
    rule_id="bim.mep.has_system",
    name="MEP elements must declare a system or system_type",
    severity="error",
    description=(
        "Mechanical/electrical/plumbing elements must expose either a "
        "'system' or 'system_type' property so they can be grouped by "
        "distribution system."
    ),
    element_filter={
        "element_type_startswith": [
            "duct",
            "pipe",
            "cabletray",
            "conduit",
            "mechanicalequipment",
            "electricalequipment",
            "plumbingfixture",
            "ifcduct",
            "ifcpipe",
            "ifccabletray",
            "ifcflowfitting",
            "ifcflowsegment",
            "ifcflowterminal",
        ],
    },
    require_any_of_properties=["system", "system_type", "system_name", "mep_system"],
)

ELEMENT_HAS_STOREY = BIMElementRule(
    rule_id="bim.element.has_storey",
    name="Elements should have a storey assignment",
    severity="warning",
    description=(
        "Elements not assigned to a storey cannot be included in "
        "storey-based reports or takeoff breakdowns. Warning only - "
        "site-wide elements like terrain or foundations are legitimately "
        "storey-less."
    ),
    require_storey=True,
)

ELEMENT_NAME_NOT_NONE = BIMElementRule(
    rule_id="bim.element.name_not_none",
    name="Elements must have a meaningful name",
    severity="warning",
    description=(
        "Elements with name == '' or 'None' indicate a broken export or "
        "an unnamed family instance. Warning severity - the rest of the "
        "data may still be usable."
    ),
    require_name=True,
)


# ── Configurable data ────────────────────────────────────────────────────────

# Minimum clear width for a single door leaf, in metres. A common accessible /
# egress clear-opening threshold; kept as a module constant so it is easy to
# tune per jurisdiction without touching rule logic.
MIN_DOOR_CLEAR_WIDTH_M = 0.85

# Category prefix -> "at least one of these properties must be present". This is
# the data-driven generalisation of the per-category "has material / has key
# property" idea: physical build elements must declare a material, spaces must
# declare a function/occupancy. Keys are matched by prefix against the
# ifc-stripped, lower-cased element type.
CATEGORY_REQUIRED_PROPERTIES: dict[str, list[str]] = {
    "wall": ["material"],
    "slab": ["material"],
    "floor": ["material"],
    "column": ["material"],
    "beam": ["material"],
    "door": ["material"],
    "window": ["material"],
    "pipe": ["material"],
    "duct": ["material"],
    "space": ["occupancy", "function", "space_type", "usage"],
    "room": ["occupancy", "function", "space_type", "usage"],
}

# Element-type prefixes considered "asset-relevant" for operational handover:
# things a facilities team tracks, maintains or replaces.
ASSET_CATEGORY_PREFIXES: list[str] = [
    "door",
    "ifcdoor",
    "window",
    "ifcwindow",
    "equipment",
    "mechanicalequipment",
    "electricalequipment",
    "plumbingfixture",
    "airterminal",
    "boiler",
    "chiller",
    "pump",
    "fan",
    "ifcpump",
    "ifcfan",
    "ifcairterminal",
    "ifcflowterminal",
    "ifcunitaryequipment",
    "ifcbuildingelementproxy",
]

# Space-like element-type prefixes (rooms / zones / spaces).
SPACE_CATEGORY_PREFIXES: list[str] = ["space", "room", "zone", "ifcspace", "ifczone"]

# Hosted element-type prefixes: openings that sit inside a host element.
HOSTED_CATEGORY_PREFIXES: list[str] = ["door", "ifcdoor", "window", "ifcwindow"]


# ── Data-driven / relational rules ───────────────────────────────────────────

CATEGORY_REQUIRED_PROPERTY = BIMElementRule(
    rule_id="bim.category.required_property",
    name="Elements must carry the key property their category requires",
    severity="warning",
    description=(
        "Data-driven completeness check. Each element category must expose at "
        "least one of the properties its category requires - a wall, slab, "
        "column, beam, door, window, pipe or duct must declare a material; a "
        "space or room must declare its function/occupancy. Generalises the "
        "per-category 'has material' checks into one configurable map."
    ),
    category_required_properties=CATEGORY_REQUIRED_PROPERTIES,
)

ELEMENT_HAS_CLASSIFICATION = BIMElementRule(
    rule_id="bim.element.has_classification",
    name="Elements should carry a classification code",
    severity="warning",
    description=(
        "Every element should carry at least one classification code (DIN 276, "
        "NRM, MasterFormat, Uniclass, ...) so it can be grouped, costed and "
        "reported by a recognised breakdown structure. Warning severity - a "
        "model can still be usable while classification is being completed."
    ),
    require_classification_code=True,
)

ASSET_HAS_TYPE_IDENTIFIER = BIMElementRule(
    rule_id="bim.asset.has_type_identifier",
    name="Asset-relevant elements should carry a type or model identifier",
    severity="info",
    description=(
        "Handover data: equipment, mechanical items, doors and windows should "
        "expose a type or model identifier so the physical item can be tied to "
        "a product, spare part or maintenance record. Informational."
    ),
    element_filter={"element_type_startswith": ASSET_CATEGORY_PREFIXES},
    require_any_of_properties=[
        "type",
        "type_name",
        "type_mark",
        "model",
        "model_number",
        "family_type",
        "family_and_type",
        "product",
    ],
)

ASSET_HAS_MARK_TAG = BIMElementRule(
    rule_id="bim.asset.has_mark_tag",
    name="Asset-relevant elements should carry a mark or tag",
    severity="info",
    description=(
        "Handover data: equipment, mechanical items, doors and windows should "
        "expose a mark, tag or asset number so the item can be found on site "
        "and in the asset register. Informational."
    ),
    element_filter={"element_type_startswith": ASSET_CATEGORY_PREFIXES},
    require_any_of_properties=["mark", "tag", "asset_tag", "asset_id", "number", "reference"],
)

SPACE_HAS_IDENTITY = BIMElementRule(
    rule_id="bim.space.identity",
    name="Spaces must have a name, a number and a positive area",
    severity="warning",
    description=(
        "Every space, room or zone must carry a name, a number or identifier, "
        "and a positive area so it can appear in room schedules and area "
        "takeoffs. A zero or missing area is flagged."
    ),
    element_filter={"element_type_startswith": SPACE_CATEGORY_PREFIXES},
    require_name=True,
    require_any_of_properties=["number", "room_number", "space_number", "mark", "identifier"],
    require_any_positive_quantity=["area_m2", "area", "net_floor_area", "gross_floor_area"],
)

HOSTED_HAS_HOST = BIMElementRule(
    rule_id="bim.hosted.has_host",
    name="Hosted elements must reference a host or parent",
    severity="warning",
    description=(
        "Hosted elements such as doors and windows must reference the host or "
        "parent element (the wall they sit in) so openings, quantities and "
        "coordination stay consistent."
    ),
    element_filter={"element_type_startswith": HOSTED_CATEGORY_PREFIXES},
    require_relation_host=True,
)

DOOR_MIN_CLEAR_WIDTH = BIMElementRule(
    rule_id="bim.door.min_clear_width",
    name="Door clear width should meet the minimum",
    severity="warning",
    description=(
        f"Doors that declare a width below the minimum clear width "
        f"({MIN_DOOR_CLEAR_WIDTH_M} m) are flagged for an egress / accessibility "
        "review. Only doors that declare a width are checked - a missing width "
        "is handled by the door dimensions rule."
    ),
    element_filter={"element_type_startswith": ["door", "ifcdoor"]},
    min_when_present={
        "paths": ["width_m", "width", "clear_width", "overall_width"],
        "min": MIN_DOOR_CLEAR_WIDTH_M,
        "label": "Door clear width",
    },
)


# ── Model-review deepening rules ──────────────────────────────────────────────

QUANTITY_NON_NEGATIVE = BIMElementRule(
    rule_id="bim.quantity.non_negative",
    name="Dimensional quantities must not be negative",
    severity="error",
    description=(
        "Dimensional quantities - areas, volumes, lengths, widths, heights, "
        "thicknesses, perimeters and counts - must never be negative. A "
        "negative dimensional value means a broken export or a bad takeoff. "
        "Directional values such as elevation or offset are not checked here; "
        "they can legitimately be below zero for basements."
    ),
    forbid_negative_quantities=True,
)

MEP_HAS_SIZE = BIMElementRule(
    rule_id="bim.mep.has_size",
    name="Distribution elements should declare a size or diameter",
    severity="warning",
    description=(
        "Ducts, pipes, cable trays and conduits should expose a size, diameter "
        "or cross-section so coordination clearances and material takeoff can be "
        "worked out. Warning severity - routing may still be reviewed while "
        "sizing is completed."
    ),
    element_filter={
        "element_type_startswith": [
            "duct",
            "pipe",
            "cabletray",
            "conduit",
            "ifcduct",
            "ifcpipe",
            "ifccabletray",
            "ifcflowsegment",
            "ifcflowfitting",
        ],
    },
    require_any_of_properties=["size", "diameter", "nominal_diameter", "dimensions", "width", "cross_section"],
)

CIRCULATION_HAS_DIMENSIONS = BIMElementRule(
    rule_id="bim.circulation.has_dimensions",
    name="Stairs and ramps should declare a width",
    severity="warning",
    description=(
        "Stairs and ramps should declare a width so egress capacity and "
        "accessibility can be reviewed. Warning severity - a width may still be "
        "added later in design."
    ),
    element_filter={
        "element_type_startswith": [
            "stair",
            "ramp",
            "ifcstair",
            "ifcramp",
            "ifcstairflight",
            "ifcrampflight",
        ],
    },
    require_any_of_properties=["width", "width_m", "clear_width", "tread_width"],
)

ELEMENT_HAS_TYPE_NAME = BIMElementRule(
    rule_id="bim.element.has_type_name",
    name="Physical elements should name their type or family",
    severity="info",
    description=(
        "Physical build elements - walls, slabs, floors, columns, beams, doors, "
        "windows, roofs, ceilings and stairs - should name their type or family "
        "so they roll up cleanly in type schedules and quantity breakdowns. "
        "Informational."
    ),
    element_filter={
        "element_type_startswith": [
            "wall",
            "slab",
            "floor",
            "column",
            "beam",
            "door",
            "window",
            "roof",
            "ceiling",
            "stair",
            "ifcwall",
            "ifcslab",
            "ifccolumn",
            "ifcbeam",
            "ifcdoor",
            "ifcwindow",
            "ifcroof",
            "ifccovering",
        ],
    },
    require_any_of_properties=["type", "type_name", "family_type", "family_and_type", "family", "type_mark"],
)

ELEMENT_HAS_PHASE = BIMElementRule(
    rule_id="bim.element.has_phase",
    name="Elements should declare a phase or status",
    severity="info",
    description=(
        "Every element should declare a phase or status - new, existing, "
        "temporary or demolished - so 4D phasing and renovation scope can be "
        "worked out and elements can be filtered by construction stage. "
        "Informational."
    ),
    require_any_of_properties=["phase", "phase_created", "construction_phase", "status", "workset_phase"],
)


# ── Registry ─────────────────────────────────────────────────────────────────

BIM_UNIVERSAL_RULES: list[BIMElementRule] = [
    WALL_HAS_THICKNESS,
    STRUCTURAL_HAS_MATERIAL,
    WALL_HAS_FIRE_RATING,
    DOOR_HAS_DIMENSIONS,
    WINDOW_HAS_DIMENSIONS,
    MEP_HAS_SYSTEM,
    ELEMENT_HAS_STOREY,
    ELEMENT_NAME_NOT_NONE,
    CATEGORY_REQUIRED_PROPERTY,
    ELEMENT_HAS_CLASSIFICATION,
    ASSET_HAS_TYPE_IDENTIFIER,
    ASSET_HAS_MARK_TAG,
    SPACE_HAS_IDENTITY,
    HOSTED_HAS_HOST,
    DOOR_MIN_CLEAR_WIDTH,
    QUANTITY_NON_NEGATIVE,
    MEP_HAS_SIZE,
    CIRCULATION_HAS_DIMENSIONS,
    ELEMENT_HAS_TYPE_NAME,
    ELEMENT_HAS_PHASE,
]
"""Ordered list of enabled universal BIM element rules."""


def get_rules_by_ids(rule_ids: list[str] | None) -> list[BIMElementRule]:
    """Return the subset of ``BIM_UNIVERSAL_RULES`` matching ``rule_ids``.

    If ``rule_ids`` is ``None`` or empty, the full enabled set is returned.
    Unknown ids are silently skipped - callers can verify by comparing
    lengths if strict behaviour is needed.
    """
    if not rule_ids:
        return [r for r in BIM_UNIVERSAL_RULES if r.enabled]
    wanted = set(rule_ids)
    return [r for r in BIM_UNIVERSAL_RULES if r.enabled and r.rule_id in wanted]
