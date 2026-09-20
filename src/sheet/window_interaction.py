from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtWidgets import QCompleter, QMenu, QTableView

from sheet.coordinates import cell_reference, parse_cell_reference
from sheet.formulas import FUNCTION_CATEGORIES, FUNCTION_HINTS
from sheet.selection import bounds

if TYPE_CHECKING:
    from sheet.window import MainWindow


@dataclass(slots=True)
class FormulaEditState:
    origin: QPersistentModelIndex
    original: str
    prefix: str
    suffix: str
    picking_range: bool = True


def setup_formula_assistance(window: MainWindow) -> None:
    completer = QCompleter(sorted(FUNCTION_HINTS), window.formula_bar)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    completer.activated.connect(lambda name: _insert_completion(window, name))
    window.formula_bar.setCompleter(completer)
    window.formula_bar.textEdited.connect(lambda _: _update_formula_help(window))
    _update_formula_help(window)


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
    if window.formula_edit is None:
        window.formula_bar.setText(window.workbook.raw_value(current.row(), current.column()))
        _update_formula_help(window)
    sync_format_controls(window, current)


def selection_changed(
    window: MainWindow, selected: QItemSelection, deselected: QItemSelection
) -> None:
    del selected, deselected
    indexes = window.table.selectionModel().selectedIndexes()
    if window.formula_edit is not None and window.formula_edit.picking_range:
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
    state = window.formula_edit
    index = state.origin if state is not None else window.table.currentIndex()
    if index.isValid():
        window.formula_edit = None
        _set_formula_range_highlight(window, False)
        window.model.setData(index, window.formula_bar.text())
        focus_cell(window, index.row(), index.column())


def cancel_formula_edit(window: MainWindow) -> None:
    state = window.formula_edit
    if state is None:
        return
    window.formula_edit = None
    _set_formula_range_highlight(window, False)
    window.formula_bar.setText(state.original)
    _update_formula_help(window)
    if state.origin.isValid():
        focus_cell(window, state.origin.row(), state.origin.column())


def function_menu(window: MainWindow) -> QMenu:
    menu = QMenu(window)
    for label, functions in FUNCTION_CATEGORIES.items():
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
    state = window.formula_edit
    if state is None:
        origin = QPersistentModelIndex(window.table.currentIndex())
        if not origin.isValid():
            return
        state = FormulaEditState(origin, window.formula_bar.text(), prefix, suffix)
        window.formula_edit = state
    else:
        state.prefix = prefix
        state.suffix = suffix
        state.picking_range = True
    window.formula_bar.setText(f"{prefix}{suffix}")
    _set_formula_range_highlight(window, True)
    window.formula_bar.setCursorPosition(len(prefix))
    window.formula_bar.setFocus()
    _update_formula_help(window)


def insert_formula_reference(window: MainWindow, indexes: list[QModelIndex]) -> None:
    state = window.formula_edit
    if not indexes or state is None:
        return
    selected = bounds((index.row(), index.column()) for index in indexes)
    if selected is None:
        return
    start = cell_reference(selected.top, selected.left)
    end = cell_reference(selected.bottom, selected.right)
    reference = start if start == end else f"{start}:{end}"
    window.formula_bar.setText(f"{state.prefix}{reference}{state.suffix}")
    window.formula_bar.setCursorPosition(len(state.prefix) + len(reference))
    _update_formula_help(window)


def stop_formula_reference(window: MainWindow) -> None:
    if window.formula_edit is not None:
        window.formula_edit.picking_range = False


def _update_formula_help(window: MainWindow) -> None:
    name = _function_name(window.formula_bar.text(), window.formula_bar.cursorPosition())
    window.function_hint.setText(FUNCTION_HINTS.get(name, ""))
    if name and window.formula_bar.hasFocus():
        completer = window.formula_bar.completer()
        if completer is not None:
            completer.setCompletionPrefix(name)
            completer.complete(window.formula_bar.cursorRect())


def _function_name(text: str, position: int) -> str:
    match = re.search(r"[A-Za-z]+$", text[:position])
    return match.group().upper() if match and text.startswith("=") else ""


def _insert_completion(window: MainWindow, name: str) -> None:
    text = window.formula_bar.text()
    position = window.formula_bar.cursorPosition()
    match = re.search(r"[A-Za-z]+$", text[:position])
    if match is None:
        return
    window.formula_bar.setText(f"{text[: match.start()]}{name}{text[position:]}")
    window.formula_bar.setCursorPosition(match.start() + len(name))
    _update_formula_help(window)


def _set_formula_range_highlight(window: MainWindow, active: bool) -> None:
    window.table.setStyleSheet(
        "QTableView::item:selected { background: #f4b942; color: #202020; }" if active else ""
    )


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
