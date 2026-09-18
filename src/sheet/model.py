from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QFont, QUndoCommand, QUndoStack

from sheet.coordinates import column_name
from sheet.formatting import CellFormat, display_value
from sheet.grid_state import GridState
from sheet.workbook import Workbook

INVALID_INDEX = QModelIndex()
type ModelIndex = QModelIndex | QPersistentModelIndex


class CellEditCommand(QUndoCommand):
    def __init__(
        self,
        model: SpreadsheetModel,
        old_values: dict[tuple[int, int], str],
        new_values: dict[tuple[int, int], str],
        text: str,
    ) -> None:
        super().__init__(text)
        self.model = model
        self.old_values = old_values
        self.new_values = new_values

    def redo(self) -> None:
        self.model._apply_cell_values(self.new_values)

    def undo(self) -> None:
        self.model._apply_cell_values(self.old_values)


class FormatCellsCommand(QUndoCommand):
    def __init__(
        self,
        model: SpreadsheetModel,
        old_formats: dict[tuple[int, int], CellFormat],
        new_formats: dict[tuple[int, int], CellFormat],
    ) -> None:
        super().__init__("Format cells")
        self.model = model
        self.old_formats = old_formats
        self.new_formats = new_formats

    def redo(self) -> None:
        self._apply(self.new_formats)

    def undo(self) -> None:
        self._apply(self.old_formats)

    def _apply(self, formats: dict[tuple[int, int], CellFormat]) -> None:
        self.model.workbook.set_formats(formats)
        self.model._emit_all_changed()


class ResizeCommand(QUndoCommand):
    def __init__(
        self,
        model: SpreadsheetModel,
        previous: tuple[int, int],
        updated: tuple[int, int],
        text: str,
    ) -> None:
        super().__init__(text)
        self.model = model
        self.previous = previous
        self.updated = updated

    def redo(self) -> None:
        self.model._apply_dimensions(self.updated)

    def undo(self) -> None:
        self.model._apply_dimensions(self.previous)


class GridStateCommand(QUndoCommand):
    def __init__(
        self, model: SpreadsheetModel, previous: GridState, updated: GridState, text: str
    ) -> None:
        super().__init__(text)
        self.model = model
        self.previous = previous
        self.updated = updated

    def redo(self) -> None:
        self.model._apply_grid_state(self.updated)

    def undo(self) -> None:
        self.model._apply_grid_state(self.previous)


class SpreadsheetModel(QAbstractTableModel):
    def __init__(self, workbook: Workbook) -> None:
        super().__init__()
        self.workbook = workbook
        self.undo_stack = QUndoStack(self)

    def rowCount(self, parent: ModelIndex = INVALID_INDEX) -> int:
        return 0 if parent.isValid() else self.workbook.rows

    def columnCount(self, parent: ModelIndex = INVALID_INDEX) -> int:
        return 0 if parent.isValid() else self.workbook.columns

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            cell_format = self.workbook.cell_format(index.row(), index.column())
            return display_value(
                self.workbook.value(index.row(), index.column()), cell_format.number_format
            )
        if role == Qt.ItemDataRole.EditRole:
            return self.workbook.raw_value(index.row(), index.column())
        if role == Qt.ItemDataRole.ForegroundRole:
            value = self.workbook.value(index.row(), index.column())
            if isinstance(value, str) and value.startswith("#"):
                return QColor("#c62828")
        if role == Qt.ItemDataRole.FontRole:
            cell_format = self.workbook.cell_format(index.row(), index.column())
            font = QFont()
            font.setBold(cell_format.bold)
            font.setItalic(cell_format.italic)
            return font
        if role == Qt.ItemDataRole.TextAlignmentRole:
            cell_format = self.workbook.cell_format(index.row(), index.column())
            if cell_format.alignment == "center":
                return Qt.AlignmentFlag.AlignCenter
            if cell_format.alignment == "right":
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if cell_format.alignment == "left":
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            value = self.workbook.value(index.row(), index.column())
            if isinstance(value, int | float) and not isinstance(value, bool):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def setData(self, index: ModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        coordinate = (index.row(), index.column())
        new_value = str(value)
        old_value = self.workbook.raw_value(*coordinate)
        if new_value == old_value:
            return False
        self.undo_stack.push(
            CellEditCommand(self, {coordinate: old_value}, {coordinate: new_value}, "Edit cell")
        )
        return True

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return column_name(section)
        return str(section + 1)

    def set_cells(self, values: dict[tuple[int, int], str], text: str = "Edit cells") -> None:
        changed = {
            coordinate: value
            for coordinate, value in values.items()
            if self.workbook.raw_value(*coordinate) != value
        }
        if not changed:
            return
        old_values = {coordinate: self.workbook.raw_value(*coordinate) for coordinate in changed}
        self.undo_stack.push(CellEditCommand(self, old_values, changed, text))

    def apply_script_changes(
        self, values: dict[tuple[int, int], str], rows: int, columns: int
    ) -> None:
        self.undo_stack.beginMacro("Run Python script")
        self.resize(rows, columns, "Resize sheet")
        self.set_cells(values, "Apply script changes")
        self.undo_stack.endMacro()

    def add_rows(self, count: int = 10) -> None:
        self.resize(self.workbook.rows + count, self.workbook.columns, "Add rows")

    def add_columns(self, count: int = 5) -> None:
        self.resize(self.workbook.rows, self.workbook.columns + count, "Add columns")

    def insert_rows(self, index: int, count: int = 1) -> None:
        self._apply_structure_change(
            self.workbook.grid_after_insert_rows(index, count), "Insert rows"
        )

    def delete_rows(self, index: int, count: int = 1) -> None:
        self._apply_structure_change(
            self.workbook.grid_after_delete_rows(index, count), "Delete rows"
        )

    def insert_columns(self, index: int, count: int = 1) -> None:
        self._apply_structure_change(
            self.workbook.grid_after_insert_columns(index, count), "Insert columns"
        )

    def delete_columns(self, index: int, count: int = 1) -> None:
        self._apply_structure_change(
            self.workbook.grid_after_delete_columns(index, count), "Delete columns"
        )

    def sort_rows(
        self, top: int, bottom: int, left: int, right: int, sort_column: int, descending: bool
    ) -> None:
        self._apply_structure_change(
            self.workbook.grid_after_sort_rows(top, bottom, left, right, sort_column, descending),
            "Sort rows",
        )

    def _apply_structure_change(self, updated: GridState, text: str) -> None:
        self.undo_stack.push(GridStateCommand(self, self.workbook.grid_state(), updated, text))

    def resize(self, rows: int, columns: int, text: str = "Resize sheet") -> None:
        previous = (self.workbook.rows, self.workbook.columns)
        updated = (rows, columns)
        if previous != updated:
            self.undo_stack.push(ResizeCommand(self, previous, updated, text))

    def apply_format(self, indexes: list[QModelIndex], **changes: Any) -> None:
        coordinates = {(index.row(), index.column()) for index in indexes}
        if not coordinates:
            return
        old_formats = {
            coordinate: self.workbook.cell_format(*coordinate) for coordinate in coordinates
        }
        new_formats = {
            coordinate: CellFormat(
                bold=current.bold if "bold" not in changes else bool(changes["bold"]),
                italic=current.italic if "italic" not in changes else bool(changes["italic"]),
                alignment=(
                    current.alignment if "alignment" not in changes else str(changes["alignment"])
                ),
                number_format=(
                    current.number_format
                    if "number_format" not in changes
                    else str(changes["number_format"])
                ),
            )
            for coordinate, current in old_formats.items()
        }
        if old_formats != new_formats:
            self.undo_stack.push(FormatCellsCommand(self, old_formats, new_formats))

    def replace_workbook(self, workbook: Workbook) -> None:
        self.beginResetModel()
        self.workbook = workbook
        self.undo_stack.clear()
        self.endResetModel()

    def refresh(self) -> None:
        self.beginResetModel()
        self.workbook.recalculate()
        self.endResetModel()

    def _apply_cell_values(self, values: dict[tuple[int, int], str]) -> None:
        old_dimensions = (self.workbook.rows, self.workbook.columns)
        grows = any(
            row >= old_dimensions[0] or column >= old_dimensions[1] for row, column in values
        )
        if grows:
            self.beginResetModel()
        self.workbook.set_cells(values)
        if grows:
            self.endResetModel()
        else:
            self._emit_all_changed()

    def _apply_dimensions(self, dimensions: tuple[int, int]) -> None:
        self.beginResetModel()
        self.workbook.resize(*dimensions)
        self.endResetModel()

    def _apply_grid_state(self, state: GridState) -> None:
        self.beginResetModel()
        self.workbook.apply_grid_state(state)
        self.endResetModel()

    def _emit_all_changed(self) -> None:
        if self.workbook.rows and self.workbook.columns:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.workbook.rows - 1, self.workbook.columns - 1),
            )
