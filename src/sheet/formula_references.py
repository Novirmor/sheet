import ast
import re
import tokenize
from collections.abc import Callable
from io import StringIO

from sheet.coordinates import CELL_REFERENCE, cell_reference, cells_in_range, parse_cell_reference

RANGE_REFERENCE = re.compile(r"\b([A-Za-z]+[1-9][0-9]*):([A-Za-z]+[1-9][0-9]*)\b")
type CoordinateTransform = Callable[[int, int], tuple[int, int] | None]


class FormulaError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_formula(formula: str) -> ast.Expression:
    expression = RANGE_REFERENCE.sub(
        lambda match: f'RANGE("{match.group(1).upper()}:{match.group(2).upper()}")',
        formula,
    )
    try:
        return ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise FormulaError("#ERROR!") from error


def formula_dependencies(formula: str) -> set[tuple[int, int]]:
    try:
        tree = parse_formula(formula)
    except FormulaError:
        return set()
    visitor = _DependencyVisitor()
    visitor.visit(tree.body)
    return visitor.coordinates


def transform_formula_references(formula: str, transform: CoordinateTransform) -> str | None:
    transformed_tokens: list[tokenize.TokenInfo] = []
    for token in tokenize.generate_tokens(StringIO(formula).readline):
        if token.type == tokenize.NAME and CELL_REFERENCE.fullmatch(token.string.upper()):
            row, column = parse_cell_reference(token.string)
            transformed = transform(row, column)
            if transformed is None:
                return None
            token = token._replace(string=cell_reference(*transformed))
        transformed_tokens.append(token)
    return tokenize.untokenize(transformed_tokens)


class _DependencyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.coordinates: set[tuple[int, int]] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if CELL_REFERENCE.fullmatch(node.id.upper()):
            self.coordinates.add(parse_cell_reference(node.id))

    def visit_Call(self, node: ast.Call) -> None:
        if self._visit_range(node):
            return
        for argument in node.args:
            self.visit(argument)

    def _visit_range(self, node: ast.Call) -> bool:
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id.upper() == "RANGE"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            return False
        start, separator, end = node.args[0].value.partition(":")
        if separator:
            self.coordinates.update(cells_in_range(start, end))
        return True
