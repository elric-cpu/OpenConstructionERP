"""Per-element BIM rules added to deepen the model-review check set.

Covers, for each new rule, a happy path, the failing case it catches, and a
sparse / missing-data case proving it never raises. Mirrors the element shape
(``SimpleNamespace``) used by ``test_bim_element_rule_hardening``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.validation.rules.bim_element_rule import (
    BIMElementRule,
    _has_classification_code,
    _has_host_reference,
    _match_category,
)
from app.modules.validation.rules.bim_universal import (
    ASSET_HAS_MARK_TAG,
    ASSET_HAS_TYPE_IDENTIFIER,
    BIM_UNIVERSAL_RULES,
    CATEGORY_REQUIRED_PROPERTY,
    DOOR_MIN_CLEAR_WIDTH,
    ELEMENT_HAS_CLASSIFICATION,
    HOSTED_HAS_HOST,
    MIN_DOOR_CLEAR_WIDTH_M,
    SPACE_HAS_IDENTITY,
)


def _elem(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": "e1",
        "name": "El",
        "element_type": "wall",
        "properties": {},
        "quantities": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── Registry wiring --------------------------------------------------------


def test_new_rules_registered_once() -> None:
    ids = [r.rule_id for r in BIM_UNIVERSAL_RULES]
    assert len(ids) == len(set(ids))  # no duplicate ids
    for rid in (
        "bim.category.required_property",
        "bim.element.has_classification",
        "bim.asset.has_type_identifier",
        "bim.asset.has_mark_tag",
        "bim.space.identity",
        "bim.hosted.has_host",
        "bim.door.min_clear_width",
    ):
        assert rid in ids


# ── 1. Category-required-property -----------------------------------------


class TestCategoryRequiredProperty:
    def test_wall_with_material_passes(self) -> None:
        wall = _elem(element_type="wall", properties={"material": "concrete"})
        assert CATEGORY_REQUIRED_PROPERTY.evaluate(wall) == []

    def test_wall_without_material_fails(self) -> None:
        wall = _elem(element_type="IfcWallStandardCase", properties={"fire_rating": "F90"})
        results = CATEGORY_REQUIRED_PROPERTY.evaluate(wall)
        assert len(results) == 1
        assert results[0].severity == "warning"

    def test_space_requires_function_not_material(self) -> None:
        ok = _elem(element_type="space", properties={"occupancy": "office"})
        missing = _elem(element_type="space", properties={"material": "air"})
        assert CATEGORY_REQUIRED_PROPERTY.evaluate(ok) == []
        assert len(CATEGORY_REQUIRED_PROPERTY.evaluate(missing)) == 1

    def test_unmapped_category_out_of_scope(self) -> None:
        # A furniture element is not in the map -> the rule does not apply.
        furniture = _elem(element_type="furniture", properties={})
        assert CATEGORY_REQUIRED_PROPERTY.matches(furniture) is False
        assert CATEGORY_REQUIRED_PROPERTY.matches(_elem(element_type="wall")) is True

    def test_sparse_element_does_not_crash(self) -> None:
        sparse = _elem(element_type=None, properties=None, quantities=None)
        assert CATEGORY_REQUIRED_PROPERTY.matches(sparse) is False
        assert CATEGORY_REQUIRED_PROPERTY.evaluate(sparse) == []

    def test_match_category_prefix(self) -> None:
        mapping = {"wall": ["material"]}
        assert _match_category(mapping, _elem(element_type="IfcWall")) == ("wall", ["material"])
        assert _match_category(mapping, _elem(element_type="door")) is None


# ── 2. Classification-code-present ----------------------------------------


class TestHasClassification:
    def test_classification_in_properties_passes(self) -> None:
        el = _elem(properties={"classification": {"din276": "330"}})
        assert ELEMENT_HAS_CLASSIFICATION.evaluate(el) == []

    def test_classification_direct_attribute_passes(self) -> None:
        el = _elem(classification={"uniclass": "Ss_25_10"})
        assert ELEMENT_HAS_CLASSIFICATION.evaluate(el) == []

    def test_missing_classification_fails(self) -> None:
        results = ELEMENT_HAS_CLASSIFICATION.evaluate(_elem(properties={"foo": "bar"}))
        assert len(results) == 1
        assert results[0].severity == "warning"

    def test_empty_classification_dict_fails(self) -> None:
        el = _elem(properties={"classification": {"din276": ""}})
        assert len(ELEMENT_HAS_CLASSIFICATION.evaluate(el)) == 1

    def test_sparse_element_does_not_crash(self) -> None:
        assert len(ELEMENT_HAS_CLASSIFICATION.evaluate(_elem(properties=None))) == 1

    def test_reader_helper(self) -> None:
        assert _has_classification_code(_elem(), {"classification": {"nrm": "2.6"}}) is True
        assert _has_classification_code(_elem(), {}) is False


# ── 3. Handover / asset completeness --------------------------------------


class TestAssetHandover:
    def test_type_identifier_present_passes(self) -> None:
        door = _elem(element_type="door", properties={"type_name": "D-90"})
        assert ASSET_HAS_TYPE_IDENTIFIER.evaluate(door) == []

    def test_type_identifier_missing_fails_info(self) -> None:
        door = _elem(element_type="door", properties={})
        results = ASSET_HAS_TYPE_IDENTIFIER.evaluate(door)
        assert len(results) == 1
        assert results[0].severity == "info"

    def test_mark_tag_present_passes(self) -> None:
        pump = _elem(element_type="MechanicalEquipment", properties={"mark": "P-01"})
        assert ASSET_HAS_MARK_TAG.evaluate(pump) == []

    def test_mark_tag_missing_fails_info(self) -> None:
        pump = _elem(element_type="mechanicalequipment", properties={})
        results = ASSET_HAS_MARK_TAG.evaluate(pump)
        assert len(results) == 1
        assert results[0].severity == "info"

    def test_non_asset_out_of_scope(self) -> None:
        wall = _elem(element_type="wall")
        assert ASSET_HAS_TYPE_IDENTIFIER.matches(wall) is False
        assert ASSET_HAS_MARK_TAG.matches(wall) is False

    def test_sparse_asset_does_not_crash(self) -> None:
        door = _elem(element_type="door", properties=None)
        assert len(ASSET_HAS_TYPE_IDENTIFIER.evaluate(door)) == 1
        assert len(ASSET_HAS_MARK_TAG.evaluate(door)) == 1


# ── 4. Space sanity -------------------------------------------------------


class TestSpaceIdentity:
    def test_complete_space_passes(self) -> None:
        space = _elem(
            element_type="space",
            name="Office 101",
            properties={"number": "101"},
            quantities={"area_m2": 15.0},
        )
        assert SPACE_HAS_IDENTITY.evaluate(space) == []

    def test_zero_area_fails(self) -> None:
        space = _elem(
            element_type="ifcspace",
            name="Office 101",
            properties={"number": "101"},
            quantities={"area_m2": 0},
        )
        assert len(SPACE_HAS_IDENTITY.evaluate(space)) == 1

    def test_missing_number_fails(self) -> None:
        space = _elem(
            element_type="room",
            name="Office",
            properties={},
            quantities={"area_m2": 12.0},
        )
        assert len(SPACE_HAS_IDENTITY.evaluate(space)) == 1

    def test_sparse_space_flags_all_but_does_not_crash(self) -> None:
        space = _elem(element_type="space", name=None, properties=None, quantities=None)
        results = SPACE_HAS_IDENTITY.evaluate(space)
        # name + number + positive-area all fail, but nothing raises.
        assert len(results) == 3

    def test_non_space_out_of_scope(self) -> None:
        assert SPACE_HAS_IDENTITY.matches(_elem(element_type="wall")) is False


# ── 5. Hosted / connected -------------------------------------------------


class TestHostedHasHost:
    def test_flat_host_key_passes(self) -> None:
        door = _elem(element_type="door", properties={"host_id": "wall-7"})
        assert HOSTED_HAS_HOST.evaluate(door) == []

    def test_relations_dict_passes(self) -> None:
        window = _elem(element_type="window", properties={"relations": {"host": "wall-3"}})
        assert HOSTED_HAS_HOST.evaluate(window) == []

    def test_missing_host_fails(self) -> None:
        door = _elem(element_type="door", properties={"width": 0.9})
        results = HOSTED_HAS_HOST.evaluate(door)
        assert len(results) == 1
        assert results[0].severity == "warning"

    def test_non_hosted_out_of_scope(self) -> None:
        assert HOSTED_HAS_HOST.matches(_elem(element_type="wall")) is False

    def test_sparse_does_not_crash(self) -> None:
        assert len(HOSTED_HAS_HOST.evaluate(_elem(element_type="door", properties=None))) == 1

    def test_reader_helper(self) -> None:
        assert _has_host_reference(_elem(), {"parent_id": "x"}) is True
        assert _has_host_reference(_elem(relations={"host": "x"}), {}) is True
        assert _has_host_reference(_elem(), {"foo": "bar"}) is False


# ── 6. Door clear width ---------------------------------------------------


class TestDoorMinClearWidth:
    def test_wide_door_passes(self) -> None:
        door = _elem(element_type="door", quantities={"width_m": 0.9})
        assert DOOR_MIN_CLEAR_WIDTH.evaluate(door) == []

    def test_narrow_door_fails(self) -> None:
        door = _elem(element_type="door", quantities={"width_m": 0.7})
        results = DOOR_MIN_CLEAR_WIDTH.evaluate(door)
        assert len(results) == 1
        assert results[0].severity == "warning"
        assert results[0].details["min"] == MIN_DOOR_CLEAR_WIDTH_M

    def test_missing_width_not_flagged(self) -> None:
        # A missing width is owned by the door-dimensions rule, not this one.
        door = _elem(element_type="door", quantities={})
        assert DOOR_MIN_CLEAR_WIDTH.evaluate(door) == []

    def test_locale_string_width(self) -> None:
        # '0,70' coerces to 0.70 -> below the minimum -> flagged.
        door = _elem(element_type="door", quantities={"width_m": "0,70"})
        assert len(DOOR_MIN_CLEAR_WIDTH.evaluate(door)) == 1

    def test_width_from_properties_fallback(self) -> None:
        door = _elem(element_type="door", quantities={}, properties={"clear_width": 0.6})
        assert len(DOOR_MIN_CLEAR_WIDTH.evaluate(door)) == 1


# ── min_when_present DSL primitive ----------------------------------------


class TestMinWhenPresentPrimitive:
    @pytest.mark.parametrize(
        ("value", "expect_fail"),
        [(0.5, True), (1.0, False), (None, False), ("abc", False)],
    )
    def test_only_present_below_min_fails(self, value: Any, expect_fail: bool) -> None:
        rule = BIMElementRule(
            rule_id="r",
            name="R",
            severity="warning",
            min_when_present={"paths": ["w"], "min": 0.85, "label": "Width"},
        )
        quants = {} if value is None else {"w": value}
        results = rule.evaluate(_elem(quantities=quants))
        assert bool(results) is expect_fail
