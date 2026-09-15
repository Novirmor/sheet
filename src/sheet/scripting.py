from collections.abc import Sequence
from typing import Any

from sheet.coordinates import cells_in_range, parse_cell_reference
from sheet.formulas import CellValue
from sheet.workbook import Workbook


class SheetAPI:
    def __init__(self, workbook: Workbook) -> None:
        self._workbook = workbook

    @property
    def rows(self) -> int:
        return self._workbook.rows

    @property
    def columns(self) -> int:
        return self._workbook.columns

    def get(self, reference: str) -> CellValue:
        row, column = parse_cell_reference(reference)
        return self._workbook.value(row, column)

    def raw(self, reference: str) -> str:
        row, column = parse_cell_reference(reference)
        return self._workbook.raw_value(row, column)

    def set(self, reference: str, value: Any) -> None:
        row, column = parse_cell_reference(reference)
        self._workbook.set_cell(row, column, "" if value is None else str(value))

    def clear(self, reference_range: str) -> None:
        for row, column in self._range_coordinates(reference_range):
            self._workbook.set_cell(row, column, "")

    def range(self, reference_range: str) -> list[list[CellValue]]:
        coordinates = list(self._range_coordinates(reference_range))
        if not coordinates:
            return []
        rows = sorted({row for row, _ in coordinates})
        columns = sorted({column for _, column in coordinates})
        return [[self._workbook.value(row, column) for column in columns] for row in rows]

    def write(self, start: str, values: Sequence[Sequence[Any]]) -> None:
        start_row, start_column = parse_cell_reference(start)
        for row_offset, row_values in enumerate(values):
            for column_offset, value in enumerate(row_values):
                self._workbook.set_cell(
                    start_row + row_offset,
                    start_column + column_offset,
                    "" if value is None else str(value),
                )

    @staticmethod
    def _range_coordinates(reference_range: str):
        start, separator, end = reference_range.upper().partition(":")
        if not separator:
            end = start
        return cells_in_range(start, end)
