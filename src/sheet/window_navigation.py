from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QInputDialog, QMenu

from sheet.window_structure import selected_columns, selected_rows

if TYPE_CHECKING:
    from sheet.window import MainWindow


def autofit_columns(window: MainWindow) -> None:
    columns = selected_columns(window)
    if columns:
        for column in columns:
            window.table.resizeColumnToContents(column)
    else:
        window.table.resizeColumnsToContents()


def autofit_rows(window: MainWindow) -> None:
    rows = selected_rows(window)
    if rows:
        for row in rows:
            window.table.resizeRowToContents(row)
    else:
        window.table.resizeRowsToContents()


def hide_rows(window: MainWindow) -> None:
    for row in selected_rows(window):
        window.table.setRowHidden(row, True)


def hide_columns(window: MainWindow) -> None:
    for column in selected_columns(window):
        window.table.setColumnHidden(column, True)


def unhide_rows(window: MainWindow) -> None:
    for row in range(window.workbook.rows):
        window.table.setRowHidden(row, False)


def unhide_columns(window: MainWindow) -> None:
    for column in range(window.workbook.columns):
        window.table.setColumnHidden(column, False)


def freeze_panes(window: MainWindow) -> None:
    index = window.table.currentIndex()
    if not index.isValid():
        return
    window.table.set_frozen_panes(index.row(), index.column())
    if index.row() or index.column():
        window.statusBar().showMessage(
            f"Frozen through row {index.row()} and column {index.column()}", 2000
        )
    else:
        window.statusBar().showMessage("Unfroze panes", 2000)


def show_filter_menu(window: MainWindow, position: QPoint) -> None:
    column = window.table.horizontalHeader().logicalIndexAt(position)
    if column < 0:
        return
    menu = QMenu(window)
    filter_action = menu.addAction("Filter column…")
    clear_action = menu.addAction("Clear all filters")
    selected = menu.exec(window.table.horizontalHeader().mapToGlobal(position))
    if selected == filter_action:
        filter_column(window, column)
    elif selected == clear_action:
        clear_filters(window)


def filter_column(window: MainWindow, column: int) -> None:
    header = window.table.horizontalHeader()
    label = window.model.headerData(column, header.orientation())
    text, accepted = QInputDialog.getText(
        window,
        "Filter column",
        f"Show rows in column {label} containing:",
        text=window.filters.get(column, ""),
    )
    if not accepted:
        return
    if text:
        window.filters[column] = text.casefold()
    else:
        window.filters.pop(column, None)
    apply_filters(window)


def clear_filters(window: MainWindow) -> None:
    window.filters.clear()
    apply_filters(window)


def apply_filters(window: MainWindow) -> None:
    for row in range(window.workbook.rows):
        visible = all(
            term in str(window.model.data(window.model.index(row, column))).casefold()
            for column, term in window.filters.items()
        )
        window.table.setRowHidden(row, not visible)
