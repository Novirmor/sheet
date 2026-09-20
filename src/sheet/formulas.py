import ast
import math
import operator
import re
from collections.abc import Callable, Iterable
from typing import ClassVar

from sheet.coordinates import CELL_REFERENCE, cells_in_range, parse_cell_reference
from sheet.formula_references import (
    FormulaError,
    formula_dependencies,
    parse_formula,
    transform_formula_references,
)

__all__ = [
    "FUNCTION_CATEGORIES",
    "FUNCTION_HINTS",
    "FormulaError",
    "FormulaEvaluator",
    "coerce_value",
    "format_value",
    "formula_dependencies",
    "transform_formula_references",
]

type CellValue = str | int | float | bool | None
type FormulaValue = CellValue | list[CellValue]
type CellResolver = Callable[[int, int], CellValue]

REFERENCE_LIKE_NAME = re.compile(r"^[A-Za-z]+[0-9]+$")
FUNCTION_CATEGORIES = {
    "Math": (
        "SUM",
        "AVERAGE",
        "MIN",
        "MAX",
        "MEDIAN",
        "COUNT",
        "COUNTA",
        "SUMIF",
        "COUNTIF",
        "ROUND",
        "ABS",
    ),
    "Text": ("CONCAT", "LEN", "LOWER", "UPPER"),
    "Logic": ("IF", "IFERROR", "AND", "OR"),
}
FUNCTION_HINTS = {
    "SUM": "SUM(number1, [number2], ...)",
    "AVERAGE": "AVERAGE(number1, [number2], ...)",
    "AVG": "AVG(number1, [number2], ...)",
    "MIN": "MIN(number1, [number2], ...)",
    "MAX": "MAX(number1, [number2], ...)",
    "MEDIAN": "MEDIAN(number1, [number2], ...)",
    "COUNT": "COUNT(value1, [value2], ...)",
    "COUNTA": "COUNTA(value1, [value2], ...)",
    "SUMIF": "SUMIF(range, criterion, [sum_range])",
    "COUNTIF": "COUNTIF(range, criterion)",
    "ROUND": "ROUND(number, [digits])",
    "ABS": "ABS(number)",
    "CONCAT": "CONCAT(value1, [value2], ...)",
    "LEN": "LEN(value)",
    "LOWER": "LOWER(text)",
    "UPPER": "UPPER(text)",
    "IF": "IF(condition, value_if_true, value_if_false)",
    "IFERROR": "IFERROR(value, fallback)",
    "AND": "AND(condition1, [condition2], ...)",
    "OR": "OR(condition1, [condition2], ...)",
}
SUPPORTED_FUNCTIONS = set(FUNCTION_HINTS) | {"RANGE"}


def coerce_value(value: str) -> CellValue:
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.upper() == "TRUE":
        return True
    if stripped.upper() == "FALSE":
        return False
    try:
        return int(stripped)
    except ValueError:
        try:
            number = float(stripped)
        except ValueError:
            return value
        return number if math.isfinite(number) else value


def format_value(value: CellValue) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class FormulaEvaluator:
    _binary_operators: ClassVar[dict[type[ast.operator], Callable[[float, float], float]]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_operators: ClassVar[dict[type[ast.unaryop], Callable[[float], float]]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }
    _comparison_operators: ClassVar[dict[type[ast.cmpop], Callable[..., bool]]] = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
    }

    def __init__(self, resolve_cell: CellResolver) -> None:
        self._resolve_cell = resolve_cell

    def evaluate(self, formula: str) -> CellValue:
        try:
            result = self._evaluate_node(parse_formula(formula).body)
        except FormulaError:
            raise
        except ZeroDivisionError as error:
            raise FormulaError("#DIV/0!") from error
        except (TypeError, ValueError) as error:
            raise FormulaError("#TYPE!") from error
        except ArithmeticError as error:
            raise FormulaError("#ERROR!") from error
        if isinstance(result, list):
            raise FormulaError("#TYPE!")
        return result

    def _evaluate_node(self, node: ast.expr) -> FormulaValue:
        if isinstance(node, ast.Constant) and isinstance(
            node.value, str | int | float | bool | None
        ):
            return node.value
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary_operators:
            left = self._number(self._scalar(self._evaluate_node(node.left)))
            right = self._number(self._scalar(self._evaluate_node(node.right)))
            return self._binary_operators[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary_operators:
            value = self._number(self._scalar(self._evaluate_node(node.operand)))
            return self._unary_operators[type(node.op)](value)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And | ast.Or):
            return self._boolean_operation(node)
        if isinstance(node, ast.Compare):
            return self._comparison(node)
        if isinstance(node, ast.IfExp):
            branch = node.body if self._truthy(self._evaluate_node(node.test)) else node.orelse
            return self._evaluate_node(branch)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id.upper()
            if name == "IF" and len(node.args) == 3:
                branch = (
                    node.args[1]
                    if self._truthy(self._evaluate_node(node.args[0]))
                    else node.args[2]
                )
                return self._evaluate_node(branch)
            if name == "IFERROR" and len(node.args) == 2:
                return self._iferror(node.args[0], node.args[1])
            arguments = [self._evaluate_node(argument) for argument in node.args]
            return self._call(name, arguments)
        raise FormulaError("#ERROR!")

    def _resolve_name(self, name: str) -> CellValue:
        normalized = name.upper()
        if normalized == "TRUE":
            return True
        if normalized == "FALSE":
            return False
        if normalized in {"NONE", "NULL"}:
            return None
        if CELL_REFERENCE.fullmatch(normalized):
            row, column = parse_cell_reference(normalized)
            return self._resolve_cell(row, column)
        if REFERENCE_LIKE_NAME.fullmatch(name):
            raise FormulaError("#REF!")
        raise FormulaError("#NAME?")

    def _boolean_operation(self, node: ast.BoolOp) -> bool:
        values = iter(node.values)
        result = self._truthy(self._evaluate_node(next(values)))
        for value_node in values:
            if isinstance(node.op, ast.And) and not result:
                return False
            if isinstance(node.op, ast.Or) and result:
                return True
            result = self._truthy(self._evaluate_node(value_node))
        return result

    def _comparison(self, node: ast.Compare) -> bool:
        left = self._scalar(self._evaluate_node(node.left))
        for comparison, right_node in zip(node.ops, node.comparators, strict=True):
            if type(comparison) not in self._comparison_operators:
                raise FormulaError("#ERROR!")
            right = self._scalar(self._evaluate_node(right_node))
            if not self._comparison_operators[type(comparison)](left, right):
                return False
            left = right
        return True

    def _call(self, name: str, arguments: list[FormulaValue]) -> FormulaValue:
        if name == "RANGE":
            return self._range(arguments)
        if name not in SUPPORTED_FUNCTIONS:
            raise FormulaError("#NAME?")
        if name in {"SUMIF", "COUNTIF"}:
            return self._conditional_function(name, arguments)
        flattened = list(self._flatten(arguments))
        if name == "AND":
            return all(self._truthy(value) for value in flattened)
        if name == "OR":
            return any(self._truthy(value) for value in flattened)
        if name in {"SUM", "AVG", "AVERAGE", "MIN", "MAX", "MEDIAN", "COUNT", "ABS", "ROUND"}:
            return self._numeric_function(name, flattened)
        if name == "COUNTA":
            return sum(value is not None for value in flattened)
        return self._text_function(name, flattened)

    def _iferror(self, value_node: ast.expr, fallback_node: ast.expr) -> FormulaValue:
        try:
            return self._scalar(self._evaluate_node(value_node))
        except FormulaError, ZeroDivisionError:
            return self._evaluate_node(fallback_node)

    def _conditional_function(self, name: str, arguments: list[FormulaValue]) -> int | float:
        if len(arguments) not in ({2} if name == "COUNTIF" else {2, 3}):
            raise FormulaError("#TYPE!")
        criteria_range, criterion = arguments[:2]
        if not isinstance(criteria_range, list):
            raise FormulaError("#TYPE!")
        target_range = arguments[2] if len(arguments) == 3 else criteria_range
        if not isinstance(target_range, list) or len(target_range) != len(criteria_range):
            raise FormulaError("#TYPE!")
        matched = [
            target
            for value, target in zip(criteria_range, target_range, strict=True)
            if _matches_criterion(value, self._scalar(criterion))
        ]
        if name == "COUNTIF":
            return len(matched)
        return sum(self._numbers(matched))

    def _range(self, arguments: list[FormulaValue]) -> list[CellValue]:
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            raise FormulaError("#REF!")
        start, separator, end = arguments[0].partition(":")
        if not separator:
            raise FormulaError("#REF!")
        return [self._resolve_cell(row, column) for row, column in cells_in_range(start, end)]

    def _numeric_function(self, name: str, flattened: list[CellValue]) -> int | float:
        values = list(self._numbers(flattened))
        if name == "SUM":
            return sum(values)
        if name in {"AVG", "AVERAGE"}:
            if not values:
                raise FormulaError("#DIV/0!")
            return sum(values) / len(values)
        if name == "MIN":
            if not values:
                raise FormulaError("#TYPE!")
            return min(values)
        if name == "MAX":
            if not values:
                raise FormulaError("#TYPE!")
            return max(values)
        if name == "MEDIAN":
            if not values:
                raise FormulaError("#TYPE!")
            ordered = sorted(values)
            middle = len(ordered) // 2
            return (
                ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
            )
        if name == "COUNT":
            return len(values)
        if name == "COUNTA":
            return sum(value is not None for value in flattened)
        if name == "ABS" and len(values) == 1:
            return abs(values[0])
        if name == "ROUND" and 1 <= len(values) <= 2:
            digits = int(values[1]) if len(values) == 2 else 0
            return round(values[0], digits)
        raise FormulaError("#TYPE!")

    @staticmethod
    def _text_function(name: str, flattened: list[CellValue]) -> int | str:
        if name == "CONCAT":
            return "".join(format_value(value) for value in flattened)
        if name == "LEN" and len(flattened) == 1:
            return len(format_value(flattened[0]))
        if name == "LOWER" and len(flattened) == 1:
            return format_value(flattened[0]).lower()
        if name == "UPPER" and len(flattened) == 1:
            return format_value(flattened[0]).upper()
        raise FormulaError("#TYPE!")

    @staticmethod
    def _scalar(value: FormulaValue) -> CellValue:
        if isinstance(value, list):
            raise FormulaError("#TYPE!")
        if isinstance(value, str) and value.startswith("#"):
            raise FormulaError(value)
        return value

    @classmethod
    def _number(cls, value: CellValue) -> float:
        scalar = cls._scalar(value)
        if scalar is None:
            return 0.0
        if isinstance(scalar, bool):
            return float(scalar)
        if isinstance(scalar, int | float):
            return float(scalar)
        raise FormulaError("#TYPE!")

    @classmethod
    def _truthy(cls, value: FormulaValue) -> bool:
        scalar = cls._scalar(value)
        return bool(scalar)

    @classmethod
    def _flatten(cls, values: Iterable[FormulaValue]) -> Iterable[CellValue]:
        for value in values:
            if isinstance(value, list):
                yield from value
            else:
                yield cls._scalar(value)

    @staticmethod
    def _numbers(values: Iterable[CellValue]) -> Iterable[int | float]:
        for value in values:
            if isinstance(value, bool):
                yield int(value)
            elif isinstance(value, int | float):
                yield value


def _matches_criterion(value: CellValue, criterion: CellValue) -> bool:
    if not isinstance(criterion, str):
        return value == criterion
    operator, target = _criterion_parts(criterion)
    if operator is None:
        return format_value(value).casefold() == criterion.casefold()
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and isinstance(target, int | float)
        and not isinstance(target, bool)
    ):
        return _compare_numbers(operator, float(value), float(target))
    if value is None or target is None:
        return False
    return _compare_text(operator, format_value(value).casefold(), format_value(target).casefold())


def _criterion_parts(criterion: str) -> tuple[str | None, CellValue]:
    for comparison_operator in (">=", "<=", "<>", ">", "<", "="):
        if criterion.startswith(comparison_operator):
            return comparison_operator, coerce_value(criterion[len(comparison_operator) :])
    return None, criterion


def _compare_numbers(operator: str, left: float, right: float) -> bool:
    if operator == "=":
        return left == right
    if operator == "<>":
        return left != right
    return _ordered_number_compare(operator, left, right)


def _compare_text(operator: str, left: str, right: str) -> bool:
    if operator == "=":
        return left == right
    if operator == "<>":
        return left != right
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    return left <= right


def _ordered_number_compare(operator: str, left: float, right: float) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    return left <= right
