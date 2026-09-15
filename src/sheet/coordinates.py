import re
from collections.abc import Iterator

CELL_REFERENCE = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


def column_name(index: int) -> str:
    if index < 0:
        raise ValueError("column index cannot be negative")

    name = ""
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def column_index(name: str) -> int:
    normalized = name.upper()
    if not normalized or not normalized.isalpha() or not normalized.isascii():
        raise ValueError(f"invalid column name: {name}")

    index = 0
    for character in normalized:
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def cell_reference(row: int, column: int) -> str:
    if row < 0:
        raise ValueError("row index cannot be negative")
    return f"{column_name(column)}{row + 1}"


def parse_cell_reference(reference: str) -> tuple[int, int]:
    match = CELL_REFERENCE.fullmatch(reference.upper())
    if match is None:
        raise ValueError(f"invalid cell reference: {reference}")
    column, row = match.groups()
    return int(row) - 1, column_index(column)


def cells_in_range(start: str, end: str) -> Iterator[tuple[int, int]]:
    start_row, start_column = parse_cell_reference(start)
    end_row, end_column = parse_cell_reference(end)
    row_bounds = sorted((start_row, end_row))
    column_bounds = sorted((start_column, end_column))
    for row in range(row_bounds[0], row_bounds[1] + 1):
        for column in range(column_bounds[0], column_bounds[1] + 1):
            yield row, column
