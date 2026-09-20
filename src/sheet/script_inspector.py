from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sheet.scripting import VariableInfo, VariablePage

ROOT_INDEX = QModelIndex()


class PreviewTableModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.columns: tuple[str, ...] = ()
        self.index_values: tuple[str, ...] = ()
        self.rows: tuple[tuple[str, ...], ...] = ()

    def set_page(self, page: VariablePage) -> None:
        self.beginResetModel()
        self.columns = page.columns
        self.index_values = page.index
        self.rows = page.rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.columns) + 1

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        if index.column() == 0:
            return self.index_values[index.row()] if index.row() < len(self.index_values) else ""
        row = self.rows[index.row()]
        return row[index.column() - 1] if index.column() - 1 < len(row) else ""

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return "index" if section == 0 else self.columns[section - 1]
        return str(section + 1)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        self.layoutAboutToBeChanged.emit()
        self.rows, self.index_values = map(
            tuple,
            zip(
                *sorted(
                    zip(self.rows, self.index_values, strict=True),
                    key=lambda item: item[1] if column == 0 else item[0][column - 1],
                    reverse=order == Qt.SortOrder.DescendingOrder,
                ),
                strict=True,
            )
            if self.rows
            else ((), ()),
        )
        self.layoutChanged.emit()


class VariableExplorer(QWidget):
    def __init__(
        self,
        inspect_page: Callable[[str, int], None],
        copy_selection: Callable[[], None],
        write_page: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._inspect_page = inspect_page
        self._copy_selection = copy_selection
        self._write_page = write_page
        self._running = False
        self.current_page: VariablePage | None = None
        self.variables = QTreeWidget()
        self.variables.setHeaderLabels(["Name", "Type", "Shape / length", "Preview"])
        self.variables.itemSelectionChanged.connect(self._selected)
        self.table_model = PreviewTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setSortingEnabled(True)
        self.status = QLabel("Run a command to inspect session variables.")
        self.previous_button = QPushButton("Previous page")
        self.next_button = QPushButton("Next page")
        self.write_button = QPushButton("Write page to sheet")
        self.copy_button = QPushButton("Copy selection")
        self.previous_button.clicked.connect(lambda: self._move_page(-1))
        self.next_button.clicked.connect(lambda: self._move_page(1))
        self.write_button.clicked.connect(self._write_page)
        self.copy_button.clicked.connect(self._copy_selection)
        controls = QHBoxLayout()
        controls.addWidget(self.status)
        controls.addStretch()
        controls.addWidget(self.previous_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.write_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.variables)
        layout.addWidget(self.table)
        layout.addLayout(controls)
        self._update_controls()

    def set_variables(self, variables: tuple[VariableInfo, ...], *, stale: bool = False) -> None:
        self.current_page = None
        self.table_model.beginResetModel()
        self.table_model.columns = ()
        self.table_model.index_values = ()
        self.table_model.rows = ()
        self.table_model.endResetModel()
        self.variables.clear()
        for variable in variables:
            shape = (
                f"{variable.rows} x {variable.columns}"
                if variable.columns
                else str(variable.rows)
                if variable.rows
                else ""
            )
            item = QTreeWidgetItem([variable.name, variable.type_name, shape, variable.summary])
            item.setData(0, Qt.ItemDataRole.UserRole, variable.handle)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, variable.type_name)
            self.variables.addTopLevelItem(item)
        self.status.setText("Variable snapshot is stale while the session runs." if stale else "")

    def set_page(self, page: VariablePage) -> None:
        self.current_page = page
        self.table_model.set_page(page)
        missing = ", ".join(str(value) for value in page.missing)
        suffix = " Preview is partial." if page.partial else ""
        self.status.setText(
            f"{page.total_rows} rows x {page.total_columns} columns. "
            f"Missing values in page: {missing}.{suffix}"
        )
        self._update_controls()

    def set_running(self, running: bool) -> None:
        self._running = running
        self.variables.setEnabled(not running)
        self.table.setEnabled(not running)
        if running and self.variables.topLevelItemCount():
            self.status.setText("Variable snapshot is stale while the session runs.")
        self._update_controls()

    def _selected(self) -> None:
        selected = self.variables.selectedItems()
        if not selected or selected[0].data(0, Qt.ItemDataRole.UserRole + 1) not in {
            "DataFrame",
            "Series",
        }:
            return
        self._inspect_page(selected[0].data(0, Qt.ItemDataRole.UserRole), 0)

    def _move_page(self, direction: int) -> None:
        if self.current_page is None:
            return
        start = max(0, self._page_start() + direction * len(self.current_page.rows))
        self._inspect_page(self.current_page.handle, start)

    def _page_start(self) -> int:
        return 0 if self.current_page is None else self.current_page.start

    def _update_controls(self) -> None:
        page = self.current_page
        enabled = not self._running and page is not None and bool(page.rows)
        self.previous_button.setEnabled(enabled and bool(page and page.start))
        self.next_button.setEnabled(enabled and bool(page and page.partial))
        self.write_button.setEnabled(enabled)
        self.copy_button.setEnabled(enabled)
