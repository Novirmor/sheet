from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QMessageBox

from sheet.workbook import Workbook

if TYPE_CHECKING:
    from sheet.window import MainWindow

NATIVE_FILE_FILTER = "Sheet document (*.sheet)"


def new_file(window: MainWindow) -> None:
    if window._maybe_save_changes():
        window._replace_workbook(Workbook(":memory:"))


def open_file(window: MainWindow) -> None:
    if not window._maybe_save_changes():
        return
    path, _ = QFileDialog.getOpenFileName(
        window, "Open spreadsheet", str(Path.home()), NATIVE_FILE_FILTER
    )
    if not path:
        return
    try:
        workbook = Workbook(Path(path))
    except (OSError, sqlite3.Error) as error:
        QMessageBox.critical(window, "Could not open spreadsheet", str(error))
        return
    window._replace_workbook(workbook)


def save(window: MainWindow) -> bool:
    window.script_workspace.sync_active_script()
    if window.workbook.path is None:
        return window._save_as()
    try:
        window.workbook.save()
    except (OSError, sqlite3.Error) as error:
        QMessageBox.critical(window, "Could not save spreadsheet", str(error))
        return False
    update_title(window)
    window.statusBar().showMessage("All changes saved", 2000)
    return True


def save_as(window: MainWindow) -> bool:
    window.script_workspace.sync_active_script()
    path = choose_save_path(window)
    if path is None:
        return False
    try:
        window.workbook.save_as(path)
    except (OSError, sqlite3.Error) as error:
        QMessageBox.critical(window, "Could not save spreadsheet", str(error))
        return False
    update_title(window)
    window.statusBar().showMessage(f"Saved to {path}", 2500)
    return True


def choose_save_path(window: MainWindow) -> Path | None:
    initial = window.workbook.path or Path.home() / "untitled.sheet"
    path, _ = QFileDialog.getSaveFileName(
        window, "Save spreadsheet", str(initial), NATIVE_FILE_FILTER
    )
    if not path:
        return None
    selected = Path(path)
    return selected if selected.suffix else selected.with_suffix(".sheet")


def maybe_save_changes(window: MainWindow) -> bool:
    window.script_workspace.sync_active_script()
    if not window.workbook.dirty:
        return True
    location = window.workbook.path.name if window.workbook.path else "this spreadsheet"
    answer = QMessageBox.question(
        window,
        "Save spreadsheet?",
        f"Save changes to {location}?",
        QMessageBox.StandardButton.Save
        | QMessageBox.StandardButton.Discard
        | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Save,
    )
    if answer == QMessageBox.StandardButton.Save:
        return window._save_as()
    if answer == QMessageBox.StandardButton.Discard:
        window.workbook.discard_changes()
        return True
    return False


def replace_workbook(window: MainWindow, workbook: Workbook) -> None:
    previous = window.workbook
    window.model.replace_workbook(workbook)
    window.script_workspace.set_model(window.model)
    previous.close()
    window._select_first_cell()
    update_title(window)


def update_title(window: MainWindow) -> None:
    name = window.workbook.path.name if window.workbook.path else "Untitled"
    modified = " *" if window.workbook.dirty else ""
    window.setWindowTitle(f"{name}{modified} — Sheet")
    if window.workbook.recovery_error is not None:
        window.document_state_label.setText("Recovery unavailable")
    elif window.workbook.dirty:
        window.document_state_label.setText("Modified")
    else:
        window.document_state_label.setText("Saved")
