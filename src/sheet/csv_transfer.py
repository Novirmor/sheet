from collections.abc import Callable, Iterable, Mapping, Sequence

from sheet.selection import CellCoordinate, bounds


def import_cells(
    rows: Sequence[Sequence[str]], start_row: int, start_column: int
) -> dict[CellCoordinate, str]:
    return {
        (start_row + row_offset, start_column + column_offset): value
        for row_offset, row in enumerate(rows)
        for column_offset, value in enumerate(row)
    }


def import_conflict_count(
    rows: Sequence[Sequence[str]],
    start_row: int,
    start_column: int,
    existing_cells: Mapping[CellCoordinate, str],
) -> int:
    return sum(
        bool(existing_cells.get((start_row + row_offset, start_column + column_offset)))
        for row_offset, row in enumerate(rows)
        for column_offset, _ in enumerate(row)
    )


def export_coordinates(
    selected: Iterable[CellCoordinate], used: Iterable[CellCoordinate]
) -> set[CellCoordinate]:
    selected_coordinates = set(selected)
    return selected_coordinates if len(selected_coordinates) > 1 else set(used)


def export_rows(
    coordinates: Iterable[CellCoordinate], value_at: Callable[[int, int], str]
) -> list[list[str]]:
    selected = bounds(coordinates)
    if selected is None:
        return []
    return [
        [value_at(row, column) for column in range(selected.left, selected.right + 1)]
        for row in range(selected.top, selected.bottom + 1)
    ]
