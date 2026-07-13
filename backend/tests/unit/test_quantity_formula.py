# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit tests for the per-element quantity formula evaluator (Issue #347).

Two layers:

* Shared-vector parity: the same fixture the frontend runs
  (``frontend/src/shared/lib/__fixtures__/elementFormula.vectors.json``) is
  replayed here so the normaliser, numeric test, variable builder and formula
  evaluator agree byte-for-byte across FE (float) and BE (Decimal).
* Backend-only guarantees: the minimal grammar rejects everything the FE
  engine would otherwise accept (function calls, power, attribute/subscript,
  comparisons, ...), Decimal exactness, and the explicit div-by-zero /
  unknown-variable errors.

Pure module, no DB - runs in the fast unit lane.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.boq.quantity_formula import (
    FormulaMathError,
    FormulaSyntaxError,
    UnknownVariableError,
    build_element_vars,
    evaluate_formula,
    is_numeric_value,
    list_formula_vars,
    normalize_var_name,
    validate_formula,
)

# Locate the shared fixture relative to the repo root (backend/ and frontend/
# are siblings). Skip the parity layer if the frontend tree is not checked out.
_VECTORS_PATH = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "src"
    / "shared"
    / "lib"
    / "__fixtures__"
    / "elementFormula.vectors.json"
)


def _load_vectors() -> dict:
    if not _VECTORS_PATH.exists():
        pytest.skip(f"shared vectors fixture not found at {_VECTORS_PATH}")
    return json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))


# ── Shared-vector parity ──────────────────────────────────────────────────


def test_param_name_vectors() -> None:
    for v in _load_vectors()["paramNames"]:
        assert normalize_var_name(v["raw"]) == v["normalized"], v


def test_numeric_vectors() -> None:
    for v in _load_vectors()["numeric"]:
        assert is_numeric_value(v["value"]) is v["numeric"], v


def test_build_vars_vectors() -> None:
    for v in _load_vectors()["buildVars"]:
        got = build_element_vars(v["quantities"], v["properties"])
        expected = {k: Decimal(str(val)) for k, val in v["expected"].items()}
        assert got == expected, v


def test_formula_eval_vectors() -> None:
    for v in _load_vectors()["formulaEval"]:
        got = evaluate_formula(v["formula"], v["vars"])
        assert got == Decimal(str(v["expected"])), v


def test_formula_error_vectors() -> None:
    for v in _load_vectors()["formulaError"]:
        with pytest.raises((FormulaSyntaxError, FormulaMathError, UnknownVariableError)):
            evaluate_formula(v["formula"], v["vars"])


# ── Backend-only grammar guarantees (stricter than the FE engine) ─────────


@pytest.mark.parametrize(
    "formula",
    [
        "min(a, b)",  # function call
        "max(1, 2)",
        "sqrt(4)",
        "2 ** 3",  # power
        "5 % 2",  # modulo
        "a.b",  # attribute access
        "a[0]",  # subscript
        "a == b",  # comparison
        "a and b",  # boolean op
        "a if b else c",  # conditional
        "[1, 2]",  # list literal
        "lambda: 1",  # lambda
        "__import__('os')",  # dunder call
        "'text'",  # string literal
        "True",  # boolean literal
    ],
)
def test_rejects_constructs_outside_minimal_grammar(formula: str) -> None:
    with pytest.raises(FormulaSyntaxError):
        validate_formula(formula)
    with pytest.raises(FormulaSyntaxError):
        evaluate_formula(formula, {"a": 1, "b": 2, "c": 3})


def test_rejects_non_finite_literal() -> None:
    with pytest.raises(FormulaSyntaxError):
        validate_formula("1e999")  # parses to a float inf Constant


def test_rejects_empty_and_overlong() -> None:
    with pytest.raises(FormulaSyntaxError):
        validate_formula("   ")
    with pytest.raises(FormulaSyntaxError):
        validate_formula("1+" * 400 + "1")  # exceeds MAX_FORMULA_LEN


def test_decimal_is_exact_not_float() -> None:
    # The classic float trap: 0.1 + 0.2 != 0.3 in binary float, but exact in
    # Decimal. Proves the evaluator never routes through float.
    assert evaluate_formula("0.1 + 0.2", {}) == Decimal("0.3")
    assert evaluate_formula("area_m2 * 0.1", {"area_m2": 3}) == Decimal("0.3")


def test_operator_precedence_and_parens() -> None:
    assert evaluate_formula("2 + 3 * 4", {}) == Decimal("14")
    assert evaluate_formula("(2 + 3) * 4", {}) == Decimal("20")
    assert evaluate_formula("-a + 5", {"a": 2}) == Decimal("3")


def test_unknown_variable_is_explicit_error() -> None:
    with pytest.raises(UnknownVariableError):
        evaluate_formula("area_m2 * 2", {})  # not a silent zero


def test_division_by_zero_is_explicit_error() -> None:
    with pytest.raises(FormulaMathError):
        evaluate_formula("5 / 0", {})
    with pytest.raises(FormulaMathError):
        evaluate_formula("a / b", {"a": 1, "b": 0})


def test_list_formula_vars_first_seen_order() -> None:
    assert list_formula_vars("length_m * height_m + length_m") == ["length_m", "height_m"]
    assert list_formula_vars("2 * 3") == []


def test_build_element_vars_skips_non_numeric_and_dedupes() -> None:
    got = build_element_vars(
        {"area_m2": 10, "label": "wall", "ok": True},
        {"Area (m2)": 999, "thickness": "0.2"},
    )
    # quantities win over a colliding normalised property key; bool/text dropped.
    assert got == {"area_m2": Decimal("10"), "thickness": Decimal("0.2")}
