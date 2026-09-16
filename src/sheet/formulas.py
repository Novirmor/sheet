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
REFERENCE_LIKE_NAME = re.compile(r"^[A-Za-z]+[0-9]+$")
SUPPORTED_FUNCTIONS = {"SUM", "AVERAGE", "AVG", "MIN", "MAX", "ABS", "ROUND", "RANGE"}


class FormulaError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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


def _parse(formula: str) -> ast.Expression:
    expression = RANGE_REFERENCE.sub(
        lambda match: f'RANGE("{match.group(1).upper()}:{match.group(2).upper()}")',
        formula,
    )
    try:
        return ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise FormulaError("#ERROR!") from error


class _DependencyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.coordinates: set[tuple[int, int]] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if CELL_REFERENCE.fullmatch(node.id.upper()):
            self.coordinates.add(parse_cell_reference(node.id))

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id.upper() == "RANGE"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
        ):
            reference_range = node.args[0].value
            if isinstance(reference_range, str):
                start, separator, end = reference_range.partition(":")
                if separator:
                    self.coordinates.update(cells_in_range(start, end))
                    return
        for argument in node.args:
            self.visit(argument)


def formula_dependencies(formula: str) -> set[tuple[int, int]]:
    try:
        tree = _parse(formula)
    except FormulaError:
        return set()
    visitor = _DependencyVisitor()
    visitor.visit(tree.body)
    return visitor.coordinates


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
            result = self._evaluate_node(_parse(formula).body)
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
            arguments = [self._evaluate_node(argument) for argument in node.args]
            return self._call(node.func.id.upper(), arguments)
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
            if len(arguments) != 1 or not isinstance(arguments[0], str):
                raise FormulaError("#REF!")
            start, separator, end = arguments[0].partition(":")
            if not separator:
                raise FormulaError("#REF!")
            return [self._resolve_cell(row, column) for row, column in cells_in_range(start, end)]
        if name not in SUPPORTED_FUNCTIONS:
            raise FormulaError("#NAME?")

        values = list(self._numbers(self._flatten(arguments)))
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
        if name == "ABS" and len(values) == 1:
            return abs(values[0])
        if name == "ROUND" and 1 <= len(values) <= 2:
            digits = int(values[1]) if len(values) == 2 else 0
            return round(values[0], digits)
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
