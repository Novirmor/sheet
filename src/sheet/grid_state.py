from collections.abc import Callable
from dataclasses import dataclass

from sheet.formatting import CellFormat
from sheet.formula_references import transform_formula_references

type CellCoordinate = tuple[int, int]
type CoordinateTransform = Callable[[int, int], CellCoordinate | None]
type SortKey = Callable[[int, int], tuple[int, float | str]]


@dataclass(frozen=True, slots=True)
class GridState:
    rows: int
    columns: int
    cells: dict[CellCoordinate, str]
    formats: dict[CellCoordinate, CellFormat]


def insert_rows(state: GridState, index: int, count: int = 1) -> GridState:
    if not 0 <= index <= state.rows or count < 1:
        raise ValueError("invalid row insertion")

    def transform(row: int, column: int) -> CellCoordinate:
        return (row + count, column) if row >= index else (row, column)

    return transform_grid(state, transform, transform, state.rows + count, state.columns)


def delete_rows(state: GridState, index: int, count: int = 1) -> GridState:
    if not 0 <= index < state.rows or count < 1 or index + count > state.rows:
        raise ValueError("invalid row deletion")
    if state.rows - count < 1:
        raise ValueError("a workbook must contain at least one row")
    end = index + count

    def transform(row: int, column: int) -> CellCoordinate | None:
        if index <= row < end:
            return None
        return (row - count, column) if row >= end else (row, column)

    return transform_grid(state, transform, transform, state.rows - count, state.columns)


def insert_columns(state: GridState, index: int, count: int = 1) -> GridState:
    if not 0 <= index <= state.columns or count < 1:
        raise ValueError("invalid column insertion")

    def transform(row: int, column: int) -> CellCoordinate:
        return (row, column + count) if column >= index else (row, column)

    return transform_grid(state, transform, transform, state.rows, state.columns + count)


def delete_columns(state: GridState, index: int, count: int = 1) -> GridState:
    if not 0 <= index < state.columns or count < 1 or index + count > state.columns:
        raise ValueError("invalid column deletion")
    if state.columns - count < 1:
        raise ValueError("a workbook must contain at least one column")
    end = index + count

    def transform(row: int, column: int) -> CellCoordinate | None:
        if index <= column < end:
            return None
        return (row, column - count) if column >= end else (row, column)

    return transform_grid(state, transform, transform, state.rows, state.columns - count)


def sort_rows(
    state: GridState,
    top: int,
    bottom: int,
    left: int,
    right: int,
    sort_column: int,
    descending: bool,
    sort_key: SortKey,
) -> GridState:
    if not (0 <= top < bottom < state.rows and 0 <= left <= sort_column <= right < state.columns):
        raise ValueError("select at least two rows to sort")
    coordinates = [
        (row, column) for row in range(top, bottom + 1) for column in range(left, right + 1)
    ]
    if any(state.cells.get(coordinate, "").startswith("=") for coordinate in coordinates):
        raise ValueError("sorting formulas is not supported")
    populated_rows = [row for row in range(top, bottom + 1) if state.cells.get((row, sort_column))]
    empty_rows = [row for row in range(top, bottom + 1) if row not in populated_rows]
    ordered_rows = sorted(
        populated_rows, key=lambda row: sort_key(row, sort_column), reverse=descending
    )
    return reorder_rows(state, coordinates, ordered_rows + empty_rows, top, left, right)


def transform_grid(
    state: GridState,
    transform_coordinate: CoordinateTransform,
    transform_reference: CoordinateTransform,
    rows: int,
    columns: int,
) -> GridState:
    cells: dict[CellCoordinate, str] = {}
    for coordinate, value in state.cells.items():
        transformed_coordinate = transform_coordinate(*coordinate)
        if transformed_coordinate is None:
            continue
        if value.startswith("="):
            transformed_formula = transform_formula_references(value[1:], transform_reference)
            value = "=#REF!" if transformed_formula is None else f"={transformed_formula}"
        cells[transformed_coordinate] = value
    formats = {
        transformed_coordinate: value
        for coordinate, value in state.formats.items()
        if (transformed_coordinate := transform_coordinate(*coordinate)) is not None
    }
    return GridState(rows, columns, cells, formats)


def reorder_rows(
    state: GridState,
    coordinates: list[CellCoordinate],
    ordered_rows: list[int],
    top: int,
    left: int,
    right: int,
) -> GridState:
    cells = dict(state.cells)
    formats = dict(state.formats)
    for coordinate in coordinates:
        cells.pop(coordinate, None)
        formats.pop(coordinate, None)
    for destination_row, source_row in zip(
        range(top, top + len(ordered_rows)), ordered_rows, strict=True
    ):
        for column in range(left, right + 1):
            source = (source_row, column)
            destination = (destination_row, column)
            if value := state.cells.get(source):
                cells[destination] = value
            if cell_format := state.formats.get(source):
                formats[destination] = cell_format
    return GridState(state.rows, state.columns, cells, formats)
