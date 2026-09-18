from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QMessageBox

from sheet.coordinates import cell_reference
from sheet.selection import bounds, contiguous_sections

if TYPE_CHECKING:
    from sheet.window import MainWindow


def insert_rows(window: MainWindow) -> None:
    index = window.table.currentIndex()
    if not index.isValid():
        return
    window.model.insert_rows(index.row())
    window._focus_cell(index.row(), index.column())


def delete_rows(window: MainWindow) -> None:
    rows = selected_rows(window)
    if not rows:
        return
    column = window.table.currentIndex().column()
    try:
        window.model.delete_rows(rows[0], len(rows))
    except ValueError as error:
        QMessageBox.warning(window, "Delete rows", str(error))
        return
    window._focus_cell(min(rows[0], window.workbook.rows - 1), column)


def insert_columns(window: MainWindow) -> None:
    index = window.table.currentIndex()
    if not index.isValid():
        return
    window.model.insert_columns(index.column())
    window._focus_cell(index.row(), index.column())


def delete_columns(window: MainWindow) -> None:
    columns = selected_columns(window)
    if not columns:
        return
    row = window.table.currentIndex().row()
    try:
        window.model.delete_columns(columns[0], len(columns))
    except ValueError as error:
        QMessageBox.warning(window, "Delete columns", str(error))
        return
    window._focus_cell(row, min(columns[0], window.workbook.columns - 1))


def sort_selection(window: MainWindow, *, descending: bool) -> None:
    coordinates = {
        (index.row(), index.column()) for index in window._selected_indexes() if index.isValid()
    }
    if len(coordinates) <= 1:
        coordinates = set(window.workbook.cells)
    if not coordinates:
        QMessageBox.information(window, "Sort selection", "There are no cells to sort.")
        return
    selected = bounds(coordinates)
    if selected is None:
        return
    current = window.table.currentIndex()
    sort_column = (
        current.column() if selected.left <= current.column() <= selected.right else selected.left
    )
    try:
        window.model.sort_rows(
            selected.top,
            selected.bottom,
            selected.left,
            selected.right,
            sort_column,
            descending,
        )
    except ValueError as error:
        QMessageBox.warning(window, "Sort selection", str(error))
        return
    window._focus_cell(selected.top, sort_column)
    direction = "descending" if descending else "ascending"
    window.statusBar().showMessage(
        f"Sorted {direction} by {cell_reference(0, sort_column)[:-1]}", 2000
    )


def selected_rows(window: MainWindow) -> list[int]:
    return selected_sections(window, lambda index: index.row())


def selected_columns(window: MainWindow) -> list[int]:
    return selected_sections(window, lambda index: index.column())


def selected_sections(window: MainWindow, section: Callable[[QModelIndex], int]) -> list[int]:
    return contiguous_sections(
        section(index) for index in window._selected_indexes() if index.isValid()
    )
