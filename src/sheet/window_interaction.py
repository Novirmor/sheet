from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex
from PySide6.QtWidgets import QMenu, QTableView

from sheet.coordinates import cell_reference, parse_cell_reference
from sheet.selection import bounds

if TYPE_CHECKING:
    from sheet.window import MainWindow


def select_first_cell(window: MainWindow) -> None:
    index = window.model.index(0, 0)
    window.table.setCurrentIndex(index)
    window.table.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)


def select_row(window: MainWindow, row: int) -> None:
    selection = QItemSelection(
        window.model.index(row, 0), window.model.index(row, window.workbook.columns - 1)
    )
    window.table.setCurrentIndex(window.model.index(row, 0))
    window.table.selectionModel().select(
        selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def select_column(window: MainWindow, column: int) -> None:
    selection = QItemSelection(
        window.model.index(0, column), window.model.index(window.workbook.rows - 1, column)
    )
    window.table.setCurrentIndex(window.model.index(0, column))
    window.table.selectionModel().select(
        selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )


def current_cell_changed(window: MainWindow, current: QModelIndex, previous: QModelIndex) -> None:
    del previous
    if not current.isValid():
        return
    reference = cell_reference(current.row(), current.column())
    window.name_box.setText(reference)
    window.position_label.setText(reference)
    if window._formula_reference_prefix is None:
        window.formula_bar.setText(window.workbook.raw_value(current.row(), current.column()))
    sync_format_controls(window, current)


def selection_changed(
    window: MainWindow, selected: QItemSelection, deselected: QItemSelection
) -> None:
    del selected, deselected
    indexes = window.table.selectionModel().selectedIndexes()
    if window._formula_reference_prefix is not None:
        insert_formula_reference(window, indexes)
    numbers = [
        float(value)
        for index in indexes
        if isinstance((value := window.workbook.value(index.row(), index.column())), int | float)
        and not isinstance(value, bool)
    ]
    if numbers:
        average = sum(numbers) / len(numbers)
        window.summary_label.setText(
            f"Count {len(numbers)}     Sum {sum(numbers):g}     Average {average:g}"
        )
    elif len(indexes) > 1:
        window.summary_label.setText(f"{len(indexes)} cells selected")
    else:
        window.summary_label.setText("Ready")


def model_changed(window: MainWindow, *args: object) -> None:
    del args
    current = window.table.currentIndex()
    if current.isValid():
        window.formula_bar.setText(window.workbook.raw_value(current.row(), current.column()))
        sync_format_controls(window, current)
    selection_changed(window, QItemSelection(), QItemSelection())
    window._update_title()


def commit_formula_bar(window: MainWindow) -> None:
    index = window.table.currentIndex()
    if index.isValid():
        window.model.setData(index, window.formula_bar.text())
        stop_formula_reference(window)
        window.table.setFocus()


def function_menu(window: MainWindow) -> QMenu:
    menu = QMenu(window)
    for label, functions in (
        ("Math", ("SUM", "AVERAGE", "MIN", "MAX", "MEDIAN", "COUNT", "COUNTA", "ROUND", "ABS")),
        ("Text", ("CONCAT", "LEN", "LOWER", "UPPER")),
        ("Logic", ("IF",)),
    ):
        submenu = menu.addMenu(label)
        for function in functions:
            action = submenu.addAction(function)
            action.triggered.connect(
                lambda checked=False, name=function: insert_function(window, name)
            )
    return menu


def insert_function(window: MainWindow, function: str) -> None:
    begin_formula_reference(window, f"={function}(", ")")


def start_formula_reference_from_bar(window: MainWindow) -> None:
    text = window.formula_bar.text()
    if text.startswith("="):
        position = window.formula_bar.cursorPosition()
        begin_formula_reference(window, text[:position], text[position:])


def begin_formula_reference(window: MainWindow, prefix: str, suffix: str) -> None:
    window._formula_reference_prefix = prefix
    window._formula_reference_suffix = suffix
    window.formula_bar.setText(f"{prefix}{suffix}")
    window.formula_bar.setCursorPosition(len(prefix))
    window.formula_bar.setFocus()


def insert_formula_reference(window: MainWindow, indexes: list[QModelIndex]) -> None:
    if not indexes or window._formula_reference_prefix is None:
        return
    selected = bounds((index.row(), index.column()) for index in indexes)
    if selected is None:
        return
    start = cell_reference(selected.top, selected.left)
    end = cell_reference(selected.bottom, selected.right)
    reference = start if start == end else f"{start}:{end}"
    window.formula_bar.setText(
        f"{window._formula_reference_prefix}{reference}{window._formula_reference_suffix}"
    )
    window.formula_bar.setCursorPosition(len(window._formula_reference_prefix) + len(reference))


def stop_formula_reference(window: MainWindow) -> None:
    window._formula_reference_prefix = None
    window._formula_reference_suffix = ""


def go_to_cell(window: MainWindow) -> None:
    try:
        row, column = parse_cell_reference(window.name_box.text().strip())
    except ValueError:
        current = window.table.currentIndex()
        window.name_box.setText(cell_reference(current.row(), current.column()))
        return
    if row >= window.workbook.rows or column >= window.workbook.columns:
        window.model.resize(
            max(window.workbook.rows, row + 1),
            max(window.workbook.columns, column + 1),
            "Expand sheet",
        )
    index = window.model.index(row, column)
    window.table.setCurrentIndex(index)
    window.table.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
    window.table.setFocus()


def selected_indexes(window: MainWindow) -> list[QModelIndex]:
    indexes = window.table.selectionModel().selectedIndexes()
    return indexes if indexes else [window.table.currentIndex()]


def apply_format(window: MainWindow, **changes: object) -> None:
    if window._updating_format_controls:
        return
    indexes = [index for index in selected_indexes(window) if index.isValid()]
    window.model.apply_format(indexes, **changes)


def number_format_changed(window: MainWindow) -> None:
    number_format = window.number_format.currentData()
    if isinstance(number_format, str):
        apply_format(window, number_format=number_format)


def sync_format_controls(window: MainWindow, index: QModelIndex) -> None:
    cell_format = window.workbook.cell_format(index.row(), index.column())
    window._updating_format_controls = True
    window.bold_action.setChecked(cell_format.bold)
    window.italic_action.setChecked(cell_format.italic)
    alignment = cell_format.alignment
    if alignment == "general":
        value = window.workbook.value(index.row(), index.column())
        alignment = (
            "right" if isinstance(value, int | float) and not isinstance(value, bool) else "left"
        )
    window.alignment_actions[alignment].setChecked(True)
    window.number_format.setCurrentIndex(window.number_format.findData(cell_format.number_format))
    window._updating_format_controls = False


def focus_cell(window: MainWindow, row: int, column: int) -> None:
    index = window.model.index(row, column)
    window.table.setCurrentIndex(index)
    window.table.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    window.table.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)


def select_range(
    window: MainWindow, start_row: int, start_column: int, rows: list[list[str]]
) -> None:
    width = max((len(row) for row in rows), default=1)
    top_left = window.model.index(start_row, start_column)
    bottom_right = window.model.index(start_row + len(rows) - 1, start_column + width - 1)
    selection = QItemSelection(top_left, bottom_right)
    window.table.selectionModel().select(
        selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )
