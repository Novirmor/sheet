import re

import pytest

from sheet.formulas import FormulaError, FormulaEvaluator, formula_dependencies


def test_formula_dependencies_include_cells_and_ranges() -> None:
    assert formula_dependencies("sum(A1:B2) + C3") == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (2, 2),
    }


def test_safe_python_expressions_support_comparisons_and_conditionals() -> None:
    values = {(0, 0): 4, (0, 1): 2}
    evaluator = FormulaEvaluator(lambda row, column: values.get((row, column)))

    assert evaluator.evaluate("A1 * B1") == 8
    assert evaluator.evaluate("A1 > B1") is True
    assert evaluator.evaluate("A1 if A1 > B1 else B1") == 4
    assert evaluator.evaluate("A1 > 0 and B1 > 0") is True


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
