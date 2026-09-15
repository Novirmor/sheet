from dataclasses import replace
from pathlib import Path

from sheet.database import SpreadsheetStore
from sheet.formatting import ALIGNMENTS, NUMBER_FORMATS, CellFormat
from sheet.formulas import CellValue, FormulaError, FormulaEvaluator, coerce_value


class Workbook:
    def __init__(self, path: str | Path) -> None:
        self.store = SpreadsheetStore(path)
        self.cells = self.store.load_cells()
        self.formats = self.store.load_formats()
        self.rows, self.columns = self.store.dimensions()
        self._values: dict[tuple[int, int], CellValue] = {}
        self.dirty = False
        self.recalculate()

    @property
    def path(self) -> Path | None:
        return self.store.path

    def close(self) -> None:
        self.store.close()

    def raw_value(self, row: int, column: int) -> str:
        return self.cells.get((row, column), "")

    def value(self, row: int, column: int) -> CellValue:
        return self._values.get((row, column))

    def set_cell(self, row: int, column: int, value: str) -> None:
        self.set_cells({(row, column): value})

    def set_cells(self, values: dict[tuple[int, int], str]) -> None:
        if not values:
            return
        maximum_row = max(row for row, _ in values)
        maximum_column = max(column for _, column in values)
        self._grow_to_include(maximum_row, maximum_column)
        normalized_values: dict[tuple[int, int], str] = {}
        for coordinate, value in values.items():
            normalized = value.strip() if value.startswith("=") else value
            normalized_values[coordinate] = normalized
            if normalized:
                self.cells[coordinate] = normalized
            else:
                self.cells.pop(coordinate, None)
        self.store.set_cells(
            (row, column, value) for (row, column), value in normalized_values.items()
        )
        self.dirty = True
        self.recalculate()

    def cell_format(self, row: int, column: int) -> CellFormat:
        return self.formats.get((row, column), CellFormat())

    def set_format(
        self,
        row: int,
        column: int,
        *,
        bold: bool | None = None,
        italic: bool | None = None,
        alignment: str | None = None,
        number_format: str | None = None,
    ) -> None:
        self._grow_to_include(row, column)
        if alignment is not None and alignment not in ALIGNMENTS:
            raise ValueError(f"invalid alignment: {alignment}")
        if number_format is not None and number_format not in NUMBER_FORMATS:
            raise ValueError(f"invalid number format: {number_format}")
        current = self.cell_format(row, column)
        updated = replace(
            current,
            bold=current.bold if bold is None else bold,
            italic=current.italic if italic is None else italic,
            alignment=current.alignment if alignment is None else alignment,
            number_format=current.number_format if number_format is None else number_format,
        )
        if updated.is_default:
            self.formats.pop((row, column), None)
        else:
            self.formats[(row, column)] = updated
        self.store.set_format(row, column, updated)
        self.dirty = True

    def resize(self, rows: int, columns: int) -> None:
        if rows < 1 or columns < 1:
            raise ValueError("a workbook must contain at least one cell")
        self.rows = rows
        self.columns = columns
        self.store.set_dimensions(rows, columns)
        self.dirty = True

    def _grow_to_include(self, row: int, column: int) -> None:
        if row < 0 or column < 0:
            raise ValueError("cell coordinates cannot be negative")
        if row >= self.rows or column >= self.columns:
            self.resize(max(self.rows, row + 1), max(self.columns, column + 1))

    def save_as(self, path: str | Path) -> None:
        destination = Path(path)
        if self.path is not None and destination.resolve() == self.path.resolve():
            self.dirty = False
            return
        replacement = SpreadsheetStore(path)
        replacement.set_dimensions(self.rows, self.columns)
        replacement.replace_cells(
            (row, column, value) for (row, column), value in self.cells.items()
        )
        replacement.replace_formats(
            (row, column, value) for (row, column), value in self.formats.items()
        )
        self.store.close()
        self.store = replacement
        self.dirty = False

    def recalculate(self) -> None:
        self._values.clear()
        for coordinate in self.cells:
            self._evaluate_cell(*coordinate, visiting=set())

    def _evaluate_cell(self, row: int, column: int, visiting: set[tuple[int, int]]) -> CellValue:
        coordinate = (row, column)
        if coordinate in self._values:
            return self._values[coordinate]
        if coordinate in visiting:
            return "#CYCLE!"

        raw_value = self.cells.get(coordinate, "")
        if not raw_value.startswith("="):
            value = coerce_value(raw_value)
            self._values[coordinate] = value
            return value

        visiting.add(coordinate)
        evaluator = FormulaEvaluator(
            lambda target_row, target_column: self._evaluate_cell(
                target_row, target_column, visiting
            )
        )
        try:
            value = evaluator.evaluate(raw_value[1:])
        except FormulaError as error:
            value = str(error)
        finally:
            visiting.remove(coordinate)
        self._values[coordinate] = value
        return value
