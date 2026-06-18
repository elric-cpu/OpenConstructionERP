# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests for the built-in methodology templates and the spec builder.

Covers the PURE parts of :mod:`app.modules.methodology.templates`:

* Catalogue invariants: the expected slugs are present (international default,
  seven popular countries, Uzbekistan, Railway industry), every template is
  internally consistent, and slugs are unique.
* ``build_cascade_spec`` / ``build_cascade_spec_from_template``: every built-in
  template builds into a valid :class:`CascadeSpec` that the pure engine
  accepts, and the produced spec carries the template's currency / decimals /
  composites / steps faithfully.
* Builder error handling: malformed composites / steps raise ``TemplateError``.

These tests import only the pure ``templates`` and ``cascade`` modules (stdlib +
dataclasses), so they run identically on local Python 3.11 and in CI.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.methodology import templates as t
from app.modules.methodology.cascade import CascadeSpec, compute_cascade

# The seven popular-country slugs migrated from the hardcoded markup tradition.
_COUNTRY_SLUGS = {
    "germany",
    "united_kingdom",
    "united_states",
    "france",
    "united_arab_emirates",
    "india",
    "australia",
}
_EXPECTED_SLUGS = _COUNTRY_SLUGS | {
    "international",
    "uzbekistan",
    "railway_infrastructure",
}


# ── Catalogue invariants ─────────────────────────────────────────────────


def test_catalogue_contains_expected_slugs() -> None:
    slugs = {tpl["slug"] for tpl in t.list_templates()}
    assert slugs >= _EXPECTED_SLUGS


def test_international_is_first_and_default_slug() -> None:
    assert t.INTERNATIONAL_SLUG == "international"
    assert t.list_templates()[0]["slug"] == "international"


def test_slugs_are_unique() -> None:
    slugs = [tpl["slug"] for tpl in t.list_templates()]
    assert len(slugs) == len(set(slugs))


def test_templates_by_slug_round_trips() -> None:
    for tpl in t.list_templates():
        assert t.get_template(tpl["slug"]) is tpl


def test_get_template_unknown_raises() -> None:
    with pytest.raises(t.TemplateError):
        t.get_template("atlantis")


@pytest.mark.parametrize("tpl", t.list_templates(), ids=lambda x: x["slug"])
def test_template_is_internally_consistent(tpl: dict) -> None:
    """Each template has the required keys and structurally valid fields."""
    for key in (
        "slug",
        "name",
        "currency",
        "decimals",
        "hierarchy_levels",
        "dimensions",
        "base_mapping",
        "composites",
        "cascade_steps",
    ):
        assert key in tpl, f"{tpl.get('slug')!r} missing {key!r}"

    assert isinstance(tpl["decimals"], int) and tpl["decimals"] >= 0

    # Hierarchy levels are ordered dicts with key/label.
    for lvl in tpl["hierarchy_levels"]:
        assert "key" in lvl and "label" in lvl

    # Every composite references only declared leaf base tokens.
    base_tokens = set(tpl["base_mapping"].keys())
    for comp_name, members in tpl["composites"].items():
        assert comp_name not in base_tokens, "composite collides with a base"
        for member in members:
            assert member in base_tokens, (
                f"{tpl['slug']}: composite {comp_name} references unknown "
                f"base {member}"
            )

    # Every step base token is a leaf base, a composite, or an earlier step.
    legal: set[str] = set(base_tokens) | set(tpl["composites"].keys())
    for step in tpl["cascade_steps"]:
        for field in ("key", "kind", "base"):
            assert field in step
        for token in step["base"]:
            assert token in legal, (
                f"{tpl['slug']}: step {step['key']} references unknown "
                f"token {token}"
            )
        legal.add(step["key"])  # later steps may reference this one


def test_no_emdash_in_template_text() -> None:
    """No em-dash or en-dash in any user-facing template string."""
    for tpl in t.list_templates():
        blob = repr(tpl)
        assert "—" not in blob, f"em-dash in template {tpl['slug']}"
        assert "–" not in blob, f"en-dash in template {tpl['slug']}"


# ── build_cascade_spec_from_template ──────────────────────────────────────


@pytest.mark.parametrize("slug", sorted(_EXPECTED_SLUGS))
def test_every_template_builds_a_valid_spec(slug: str) -> None:
    """Each built-in template builds a spec the pure engine accepts."""
    spec = t.build_cascade_spec_from_template(slug)
    assert isinstance(spec, CascadeSpec)
    assert spec.slug == slug
    tpl = t.get_template(slug)
    assert spec.currency == tpl["currency"]
    assert spec.decimals == tpl["decimals"]
    assert len(spec.steps) == len(tpl["cascade_steps"])

    # Build a trivial bases map (one unit per leaf base) and confirm the engine
    # runs end-to-end without raising - i.e. no forward refs / unknown tokens.
    bases = {token: Decimal("1") for token in tpl["base_mapping"].keys()}
    if not bases:
        bases = {"direct": Decimal("1")}
    result = compute_cascade(spec, bases)
    assert result.grand_total >= result.direct_total


def test_uzbekistan_spec_has_smr_composite_and_vat_step() -> None:
    spec = t.build_cascade_spec_from_template("uzbekistan")
    assert "SMR" in spec.composites
    assert spec.composites["SMR"] == ("labor", "machinery", "materials")
    keys = [s.key for s in spec.steps]
    assert keys[-1] == "vat"
    # VAT applies to SMR + equipment + every prior step.
    vat = spec.steps[-1]
    assert "SMR" in vat.base and "equipment" in vat.base


def test_rates_are_decimal_on_built_spec() -> None:
    """Rates survive the str -> Decimal coercion without float contamination."""
    spec = t.build_cascade_spec_from_template("germany")
    for step in spec.steps:
        assert isinstance(step.rate, Decimal)
        assert isinstance(step.amount, Decimal)


# ── build_cascade_spec error handling ─────────────────────────────────────


def test_build_spec_rejects_non_mapping_composites() -> None:
    with pytest.raises(t.TemplateError):
        t.build_cascade_spec(
            slug="x",
            currency="",
            decimals=2,
            composites=[("SMR", ["labor"])],  # type: ignore[arg-type]
            cascade_steps=[],
        )


def test_build_spec_rejects_string_composite_members() -> None:
    with pytest.raises(t.TemplateError):
        t.build_cascade_spec(
            slug="x",
            currency="",
            decimals=2,
            composites={"SMR": "labor"},  # bare string, not a list
            cascade_steps=[],
        )


def test_build_spec_rejects_step_missing_key() -> None:
    with pytest.raises(t.TemplateError):
        t.build_cascade_spec(
            slug="x",
            currency="",
            decimals=2,
            composites={},
            cascade_steps=[{"kind": "percentage", "rate": "5", "base": []}],
        )


def test_build_spec_rejects_non_mapping_step() -> None:
    with pytest.raises(t.TemplateError):
        t.build_cascade_spec(
            slug="x",
            currency="",
            decimals=2,
            composites={},
            cascade_steps=["overhead"],  # type: ignore[list-item]
        )


def test_build_spec_rejects_string_step_base() -> None:
    with pytest.raises(t.TemplateError):
        t.build_cascade_spec(
            slug="x",
            currency="",
            decimals=2,
            composites={},
            cascade_steps=[
                {"key": "o", "kind": "percentage", "rate": "5", "base": "direct"}
            ],
        )


def test_build_spec_defaults_blank_rate_to_zero() -> None:
    """An empty-string rate (a blank UI field) coerces to Decimal('0')."""
    spec = t.build_cascade_spec(
        slug="x",
        currency="USD",
        decimals=2,
        composites={"d": ["labor"]},
        cascade_steps=[
            {"key": "o", "label": "O", "category": "overhead", "kind": "percentage", "rate": "", "base": ["d"]}
        ],
    )
    assert spec.steps[0].rate == Decimal("0")
