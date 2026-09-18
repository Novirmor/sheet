import re

import pytest

from sheet.formulas import (
    FormulaError,
    FormulaEvaluator,
    formula_dependencies,
    transform_formula_references,
)


def test_formula_dependencies_include_cells_and_ranges() -> None:
    assert formula_dependencies("sum(A1:B2) + C3") == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (2, 2),
    }


def test_formula_reference_transform_leaves_string_literals_unchanged() -> None:
    assert (
        transform_formula_references('A1 + B2 + "A1"', lambda row, column: (row + 1, column))
        == 'A2 + B3 + "A1"'
    )


def test_safe_python_expressions_support_comparisons_and_conditionals() -> None:
    values = {(0, 0): 4, (0, 1): 2}
    evaluator = FormulaEvaluator(lambda row, column: values.get((row, column)))

    assert evaluator.evaluate("A1 * B1") == 8
    assert evaluator.evaluate("A1 > B1") is True
    assert evaluator.evaluate("A1 if A1 > B1 else B1") == 4
    assert evaluator.evaluate("A1 > 0 and B1 > 0") is True


def test_common_math_text_and_logic_functions() -> None:
    values = {(0, 0): 2, (1, 0): 4, (0, 1): "Hello"}
    evaluator = FormulaEvaluator(lambda row, column: values.get((row, column)))

    assert evaluator.evaluate("COUNT(A1:A2)") == 2
    assert evaluator.evaluate("COUNTA(A1:B2)") == 3
    assert evaluator.evaluate("MEDIAN(A1:A2)") == 3
    assert evaluator.evaluate('CONCAT(B1, " world")') == "Hello world"
    assert evaluator.evaluate("LOWER(B1)") == "hello"
    assert evaluator.evaluate("UPPER(B1)") == "HELLO"
    assert evaluator.evaluate("LEN(B1)") == 5
    assert evaluator.evaluate("IF(A1 > 0, A1, 1 / 0)") == 2


@pytest.mark.parametrize(
    ("formula", "code"),
    [
        ("1 / 0", "#DIV/0!"),
        ("A0", "#REF!"),
        ("'text' + 1", "#TYPE!"),
        ("unknown_function(1)", "#NAME?"),
        ("__import__('os')", "#NAME?"),
        ("(1).__class__", "#ERROR!"),
    ],
)
def test_unsafe_or_invalid_formulas_return_specific_errors(formula: str, code: str) -> None:
    evaluator = FormulaEvaluator(lambda row, column: None)

    with pytest.raises(FormulaError, match=f"^{re.escape(code)}$"):
        evaluator.evaluate(formula)
