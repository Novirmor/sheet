import ast
import math
import operator
import re
from collections.abc import Callable, Iterable
from typing import ClassVar

from sheet.coordinates import CELL_REFERENCE, cells_in_range, parse_cell_reference

type CellValue = str | int | float | bool | None
type FormulaValue = CellValue | list[CellValue]
type CellResolver = Callable[[int, int], CellValue]

RANGE_REFERENCE = re.compile(r"\b([A-Za-z]+[1-9][0-9]*):([A-Za-z]+[1-9][0-9]*)\b")


class FormulaError(Exception):
    pass


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
    _binary_operators: ClassVar[dict[type[ast.operator], Callable[..., CellValue]]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _unary_operators: ClassVar[dict[type[ast.unaryop], Callable[..., CellValue]]] = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def __init__(self, resolve_cell: CellResolver) -> None:
        self._resolve_cell = resolve_cell

    def evaluate(self, formula: str) -> CellValue:
        expression = RANGE_REFERENCE.sub(
            lambda match: f'RANGE("{match.group(1).upper()}:{match.group(2).upper()}")',
            formula,
        )
        try:
            tree = ast.parse(expression, mode="eval")
            result = self._evaluate_node(tree.body)
        except ZeroDivisionError as error:
            raise FormulaError("#DIV/0!") from error
        except (ArithmeticError, SyntaxError, TypeError, ValueError) as error:
            raise FormulaError("#ERROR!") from error
        if isinstance(result, list):
            raise FormulaError("#ERROR!")
        return result

    def _evaluate_node(self, node: ast.expr) -> FormulaValue:
        if isinstance(node, ast.Constant) and isinstance(node.value, str | int | float | bool):
            return node.value
        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary_operators:
            left = self._scalar(self._evaluate_node(node.left))
            right = self._scalar(self._evaluate_node(node.right))
            return self._binary_operators[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary_operators:
            return self._unary_operators[type(node.op)](
                self._scalar(self._evaluate_node(node.operand))
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            arguments = [self._evaluate_node(argument) for argument in node.args]
            return self._call(node.func.id.upper(), arguments)
        raise FormulaError("#ERROR!")

    def _resolve_name(self, name: str) -> CellValue:
        normalized = name.upper()
        if CELL_REFERENCE.fullmatch(normalized) is None:
            raise FormulaError("#NAME?")
        row, column = parse_cell_reference(normalized)
        return self._resolve_cell(row, column)

    def _call(self, name: str, arguments: list[FormulaValue]) -> FormulaValue:
        if name == "RANGE" and len(arguments) == 1 and isinstance(arguments[0], str):
            start, separator, end = arguments[0].partition(":")
            if not separator:
                raise FormulaError("#REF!")
            return [self._resolve_cell(row, column) for row, column in cells_in_range(start, end)]

        values = list(self._numbers(self._flatten(arguments)))
        if name == "SUM":
            return sum(values)
        if name in {"AVG", "AVERAGE"}:
            if not values:
                raise FormulaError("#DIV/0!")
            return sum(values) / len(values)
        if name == "MIN":
            return min(values)
        if name == "MAX":
            return max(values)
        if name == "ABS" and len(values) == 1:
            return abs(values[0])
        if name == "ROUND" and 1 <= len(values) <= 2:
            digits = int(values[1]) if len(values) == 2 else 0
            return round(values[0], digits)
        raise FormulaError("#NAME?")

    @staticmethod
    def _scalar(value: FormulaValue) -> CellValue:
        if isinstance(value, list):
            raise FormulaError("#ERROR!")
        if value is None:
            return 0
        return value

    @staticmethod
    def _flatten(values: Iterable[FormulaValue]) -> Iterable[CellValue]:
        for value in values:
            if isinstance(value, list):
                yield from value
            else:
                yield value

    @staticmethod
    def _numbers(values: Iterable[CellValue]) -> Iterable[int | float]:
        for value in values:
            if isinstance(value, bool):
                yield int(value)
            elif isinstance(value, int | float):
                yield value
