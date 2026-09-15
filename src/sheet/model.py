from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QFont, QUndoCommand, QUndoStack

from sheet.coordinates import column_name
from sheet.formatting import CellFormat, display_value
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
        changes: dict[str, Any],
    ) -> None:
        super().__init__("Format cells")
        self.model = model
        self.old_formats = old_formats
        self.new_formats: dict[tuple[int, int], CellFormat] = {}
        for coordinate in old_formats:
            row, column = coordinate
            model.workbook.set_format(row, column, **changes)
            self.new_formats[coordinate] = model.workbook.cell_format(row, column)
            model.workbook.set_format(
                row,
                column,
                bold=old_formats[coordinate].bold,
                italic=old_formats[coordinate].italic,
                alignment=old_formats[coordinate].alignment,
                number_format=old_formats[coordinate].number_format,
            )

    def redo(self) -> None:
        self._apply(self.new_formats)

    def undo(self) -> None:
        self._apply(self.old_formats)

    def _apply(self, formats: dict[tuple[int, int], CellFormat]) -> None:
        for (row, column), cell_format in formats.items():
            self.model.workbook.set_format(
                row,
                column,
                bold=cell_format.bold,
                italic=cell_format.italic,
                alignment=cell_format.alignment,
                number_format=cell_format.number_format,
            )
        self.model._emit_all_changed()


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

    def add_rows(self, count: int = 10) -> None:
        first = self.workbook.rows
        last = first + count - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self.workbook.resize(self.workbook.rows + count, self.workbook.columns)
        self.endInsertRows()

    def add_columns(self, count: int = 5) -> None:
        first = self.workbook.columns
        last = first + count - 1
        self.beginInsertColumns(QModelIndex(), first, last)
        self.workbook.resize(self.workbook.rows, self.workbook.columns + count)
        self.endInsertColumns()

    def apply_format(self, indexes: list[QModelIndex], **changes: Any) -> None:
        coordinates = {(index.row(), index.column()) for index in indexes}
        if not coordinates:
            return
        old_formats = {
            coordinate: self.workbook.cell_format(*coordinate) for coordinate in coordinates
        }
        self.undo_stack.push(FormatCellsCommand(self, old_formats, changes))

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

    def _emit_all_changed(self) -> None:
        if self.workbook.rows and self.workbook.columns:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.workbook.rows - 1, self.workbook.columns - 1),
            )
