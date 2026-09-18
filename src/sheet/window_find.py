from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sheet.coordinates import cell_reference
from sheet.find_dialog import FindReplaceDialog

if TYPE_CHECKING:
    from sheet.window import MainWindow


def show_find_replace(window: MainWindow) -> None:
    if not hasattr(window, "find_dialog"):
        window.find_dialog = FindReplaceDialog(
            window._find_next, window._replace_next, window._replace_all, window
        )
    window.find_dialog.show()
    window.find_dialog.raise_()
    window.find_dialog.activateWindow()
    window.find_dialog.find_input.setFocus()


def find_next(window: MainWindow, search: str, match_case: bool) -> bool:
    if not search:
        return False
    coordinates = _search_order(window)
    for row, column in coordinates:
        if matches(window.workbook.raw_value(row, column), search, match_case):
            window._focus_cell(row, column)
            window.statusBar().showMessage(f"Found in {cell_reference(row, column)}", 1800)
            return True
    window.statusBar().showMessage(f'No matches for "{search}"', 1800)
    return False


def replace_next(window: MainWindow, search: str, replacement: str, match_case: bool) -> bool:
    if not search:
        return False
    current = window.table.currentIndex()
    if not current.isValid() or not matches(
        window.workbook.raw_value(current.row(), current.column()), search, match_case
    ):
        return find_next(window, search, match_case)
    coordinate = (current.row(), current.column())
    value = replace_value(window.workbook.raw_value(*coordinate), search, replacement, match_case)
    window.model.set_cells({coordinate: value}, "Replace cell")
    return find_next(window, search, match_case)


def replace_all(window: MainWindow, search: str, replacement: str, match_case: bool) -> int:
    if not search:
        return 0
    changes = {
        coordinate: replace_value(value, search, replacement, match_case)
        for coordinate, value in window.workbook.cells.items()
        if matches(value, search, match_case)
    }
    window.model.set_cells(changes, "Replace all")
    count = len(changes)
    window.statusBar().showMessage(f"Replaced {count} cell(s)", 1800)
    return count


def matches(value: str, search: str, match_case: bool) -> bool:
    return search in value if match_case else search.casefold() in value.casefold()


def replace_value(value: str, search: str, replacement: str, match_case: bool) -> str:
    if match_case:
        return value.replace(search, replacement, 1)
    return re.sub(re.escape(search), replacement, value, count=1, flags=re.IGNORECASE)


def _search_order(window: MainWindow) -> list[tuple[int, int]]:
    coordinates = sorted(window.workbook.cells)
    current = window.table.currentIndex()
    if not current.isValid():
        return coordinates
    current_coordinate = (current.row(), current.column())
    return [coordinate for coordinate in coordinates if coordinate > current_coordinate] + [
        coordinate for coordinate in coordinates if coordinate <= current_coordinate
    ]
