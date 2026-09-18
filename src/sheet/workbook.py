import uuid
from dataclasses import replace
from pathlib import Path

from sheet.database import SpreadsheetStore
from sheet.formatting import ALIGNMENTS, NUMBER_FORMATS, CellFormat
from sheet.formulas import (
    CellValue,
    FormulaError,
    FormulaEvaluator,
    coerce_value,
    formula_dependencies,
)
from sheet.grid_state import (
    GridState,
    delete_columns,
    delete_rows,
    insert_columns,
    insert_rows,
    sort_rows,
)
from sheet.workbook_storage import (
    RecoverySnapshot,
    discard_snapshot,
    find_recovery_snapshots,
    user_recovery_directory,
    write_snapshot,
)


class Workbook:
    def __init__(self, path: str | Path, *, recovery_enabled: bool = True) -> None:
        self._path = Path(path) if path != ":memory:" else None
        self._recovery_id = uuid.uuid4().hex
        self._recovery_enabled = recovery_enabled
        self.store = SpreadsheetStore(":memory:")
        source_metadata: dict[str, str] = {}
        if self._path is not None and self._path.exists():
            source = SpreadsheetStore(self._path)
            try:
                rows, columns = source.dimensions()
                self.store.set_dimensions(rows, columns)
                self.store.replace_cells(
                    (row, column, value) for (row, column), value in source.load_cells().items()
                )
                self.store.replace_formats(
                    (row, column, value) for (row, column), value in source.load_formats().items()
                )
                self.store.replace_scripts(source.load_scripts().items())
                source_metadata = source.metadata()
            finally:
                source.close()
        if recovery_id := source_metadata.get("recovery_id"):
            self._recovery_id = recovery_id
        self.cells = self.store.load_cells()
        self.formats = self.store.load_formats()
        self.scripts = self.store.load_scripts()
        self.rows, self.columns = self.store.dimensions()
        self._values: dict[tuple[int, int], CellValue] = {}
        self._dependencies: dict[tuple[int, int], set[tuple[int, int]]] = {}
        self._dependents: dict[tuple[int, int], set[tuple[int, int]]] = {}
        self.dirty = False
        self.recovery_error: OSError | None = None
        self._rebuild_dependencies()
        self.recalculate()

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def recovery_path(self) -> Path:
        return self.recovery_directory() / f"{self._recovery_id}.sheet"

    @staticmethod
    def recovery_directory() -> Path:
        return user_recovery_directory()

    @classmethod
    def recovery_snapshots(cls) -> list[RecoverySnapshot]:
        return find_recovery_snapshots(cls.recovery_directory())

    @classmethod
    def from_recovery(cls, snapshot: RecoverySnapshot) -> Workbook:
        workbook = cls(snapshot.path)
        workbook._path = snapshot.source
        workbook.dirty = True
        return workbook

    @staticmethod
    def discard_recovery(snapshot: RecoverySnapshot) -> None:
        discard_snapshot(snapshot.path)

    def close(self) -> None:
        if self.dirty and self._recovery_enabled:
            self._update_recovery_snapshot()
        else:
            self.discard_recovery_snapshot()
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
        self._grow_to_include(maximum_row, maximum_column, write_recovery=False)
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
        for coordinate in normalized_values:
            self._update_dependencies(coordinate)
        self._mark_modified()
        self.recalculate(self._affected_cells(set(normalized_values)))

    def grid_state(self) -> GridState:
        return GridState(self.rows, self.columns, dict(self.cells), dict(self.formats))

    def apply_grid_state(self, state: GridState) -> None:
        self.rows = state.rows
        self.columns = state.columns
        self.cells = dict(state.cells)
        self.formats = dict(state.formats)
        self.store.set_dimensions(self.rows, self.columns)
        self.store.replace_cells(
            (row, column, value) for (row, column), value in self.cells.items()
        )
        self.store.replace_formats(
            (row, column, value) for (row, column), value in self.formats.items()
        )
        self._rebuild_dependencies()
        self._mark_modified()
        self.recalculate()

    def grid_after_insert_rows(self, index: int, count: int = 1) -> GridState:
        return insert_rows(self.grid_state(), index, count)

    def grid_after_delete_rows(self, index: int, count: int = 1) -> GridState:
        return delete_rows(self.grid_state(), index, count)

    def grid_after_insert_columns(self, index: int, count: int = 1) -> GridState:
        return insert_columns(self.grid_state(), index, count)

    def grid_after_delete_columns(self, index: int, count: int = 1) -> GridState:
        return delete_columns(self.grid_state(), index, count)

    def grid_after_sort_rows(
        self, top: int, bottom: int, left: int, right: int, sort_column: int, descending: bool
    ) -> GridState:
        return sort_rows(
            self.grid_state(), top, bottom, left, right, sort_column, descending, self._sort_key
        )

    def _sort_key(self, row: int, column: int) -> tuple[int, float | str]:
        value = self.value(row, column)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return 0, float(value)
        return 1, str(value).casefold() if value is not None else ""

    def set_script(self, name: str, source: str) -> None:
        if not name.strip():
            raise ValueError("a script must have a name")
        if self.scripts.get(name) == source:
            return
        self.scripts[name] = source
        self.store.replace_scripts(self.scripts.items())
        self._mark_modified()

    def delete_script(self, name: str) -> None:
        if name not in self.scripts:
            return
        self.scripts.pop(name)
        self.store.replace_scripts(self.scripts.items())
        self._mark_modified()

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
        current = self.cell_format(row, column)
        updated = replace(
            current,
            bold=current.bold if bold is None else bold,
            italic=current.italic if italic is None else italic,
            alignment=current.alignment if alignment is None else alignment,
            number_format=current.number_format if number_format is None else number_format,
        )
        self.set_formats({(row, column): updated})

    def set_formats(self, formats: dict[tuple[int, int], CellFormat]) -> None:
        if not formats:
            return
        maximum_row = max(row for row, _ in formats)
        maximum_column = max(column for _, column in formats)
        self._grow_to_include(maximum_row, maximum_column, write_recovery=False)
        for coordinate, cell_format in formats.items():
            self._validate_format(cell_format)
            if cell_format.is_default:
                self.formats.pop(coordinate, None)
            else:
                self.formats[coordinate] = cell_format
        self.store.set_formats((row, column, value) for (row, column), value in formats.items())
        self._mark_modified()

    def resize(self, rows: int, columns: int) -> None:
        self._resize(rows, columns, write_recovery=True)

    def _resize(self, rows: int, columns: int, *, write_recovery: bool) -> None:
        if rows < 1 or columns < 1:
            raise ValueError("a workbook must contain at least one cell")
        if (rows, columns) == (self.rows, self.columns):
            return
        self.rows = rows
        self.columns = columns
        self.store.set_dimensions(rows, columns)
        if write_recovery:
            self._mark_modified()
        else:
            self.dirty = True

    def _grow_to_include(self, row: int, column: int, *, write_recovery: bool) -> None:
        if row < 0 or column < 0:
            raise ValueError("cell coordinates cannot be negative")
        if row >= self.rows or column >= self.columns:
            self._resize(
                max(self.rows, row + 1),
                max(self.columns, column + 1),
                write_recovery=write_recovery,
            )

    def save(self) -> None:
        if self._path is None:
            raise ValueError("an untitled workbook needs a save path")
        self._write_database(self._path)
        self.dirty = False
        self.discard_recovery_snapshot()

    def save_as(self, path: str | Path) -> None:
        destination = Path(path)
        self._write_database(destination)
        self._path = destination
        self.dirty = False
        self.discard_recovery_snapshot()

    def write_recovery_snapshot(self) -> None:
        self._write_database(self.recovery_path, recovery=True)

    def discard_recovery_snapshot(self) -> None:
        discard_snapshot(self.recovery_path)

    def discard_changes(self) -> None:
        self.dirty = False
        self.discard_recovery_snapshot()

    def _mark_modified(self) -> None:
        self.dirty = True
        self._update_recovery_snapshot()

    def _update_recovery_snapshot(self) -> None:
        if not self._recovery_enabled:
            return
        try:
            self.write_recovery_snapshot()
        except OSError as error:
            self.recovery_error = error
        else:
            self.recovery_error = None

    def _write_database(self, destination: Path, *, recovery: bool = False) -> None:
        metadata = (
            {
                "recovery_source": str(self._path) if self._path else "",
                "recovery_id": self._recovery_id,
            }
            if recovery
            else None
        )
        write_snapshot(
            destination,
            rows=self.rows,
            columns=self.columns,
            cells=self.cells,
            formats=self.formats,
            scripts=self.scripts,
            metadata=metadata,
        )

    @staticmethod
    def _validate_format(cell_format: CellFormat) -> None:
        if cell_format.alignment not in ALIGNMENTS:
            raise ValueError(f"invalid alignment: {cell_format.alignment}")
        if cell_format.number_format not in NUMBER_FORMATS:
            raise ValueError(f"invalid number format: {cell_format.number_format}")

    def recalculate(self, coordinates: set[tuple[int, int]] | None = None) -> None:
        targets = set(self.cells) if coordinates is None else coordinates
        for coordinate in targets:
            self._values.pop(coordinate, None)
        for coordinate in targets:
            self._evaluate_cell(*coordinate, visiting=set())

    def _rebuild_dependencies(self) -> None:
        self._dependencies.clear()
        self._dependents.clear()
        for coordinate in self.cells:
            self._update_dependencies(coordinate)

    def _update_dependencies(self, coordinate: tuple[int, int]) -> None:
        for dependency in self._dependencies.pop(coordinate, set()):
            dependents = self._dependents.get(dependency)
            if dependents is not None:
                dependents.discard(coordinate)
                if not dependents:
                    self._dependents.pop(dependency, None)

        raw_value = self.cells.get(coordinate, "")
        if not raw_value.startswith("="):
            return
        dependencies = formula_dependencies(raw_value[1:])
        self._dependencies[coordinate] = dependencies
        for dependency in dependencies:
            self._dependents.setdefault(dependency, set()).add(coordinate)

    def _affected_cells(self, changed: set[tuple[int, int]]) -> set[tuple[int, int]]:
        affected = set(changed)
        pending = list(changed)
        while pending:
            coordinate = pending.pop()
            for dependent in self._dependents.get(coordinate, set()):
                if dependent not in affected:
                    affected.add(dependent)
                    pending.append(dependent)
        return affected

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
        if raw_value == "=#REF!":
            self._values[coordinate] = "#REF!"
            return "#REF!"

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
