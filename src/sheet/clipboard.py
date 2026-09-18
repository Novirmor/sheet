from collections.abc import Callable, Iterable

from sheet.selection import CellCoordinate, bounds


def copy_text(coordinates: Iterable[CellCoordinate], value_at: Callable[[int, int], str]) -> str:
    selected = set(coordinates)
    cell_range = bounds(selected)
    if cell_range is None:
        return ""
    lines = []
    for row in range(cell_range.top, cell_range.bottom + 1):
        fields = []
        for column in range(cell_range.left, cell_range.right + 1):
            value = value_at(row, column) if (row, column) in selected else ""
            fields.append(value.replace("\t", " ").replace("\n", " "))
        lines.append("\t".join(fields))
    return "\n".join(lines)


def paste_rows(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.splitlines()] or [[""]]
