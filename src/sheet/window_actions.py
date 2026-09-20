from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QStyle

if TYPE_CHECKING:
    from sheet.window import MainWindow


def build_actions(window: MainWindow) -> None:
    style = window.style()
    _build_file_actions(window, style)
    _build_edit_actions(window, style)
    _build_format_actions(window)
    _build_sheet_actions(window)
    _build_script_action(window, style)


def _build_file_actions(window: MainWindow, style: QStyle) -> None:
    window.new_action = QAction(
        style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), "&New", window
    )
    window.new_action.setShortcut(QKeySequence.StandardKey.New)
    window.new_action.setStatusTip("Create a new spreadsheet")
    window.new_action.triggered.connect(window._new_file)

    window.open_action = QAction(
        style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "&Open…", window
    )
    window.open_action.setShortcut(QKeySequence.StandardKey.Open)
    window.open_action.setStatusTip("Open a Sheet database")
    window.open_action.triggered.connect(window._open_file)

    window.save_action = QAction(
        style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "&Save", window
    )
    window.save_action.setShortcut(QKeySequence.StandardKey.Save)
    window.save_action.triggered.connect(window._save)

    window.save_as_action = QAction("Save &As…", window)
    window.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
    window.save_as_action.triggered.connect(window._save_as)

    window.import_csv_action = QAction("Import &CSV…", window)
    window.import_csv_action.setShortcut("Ctrl+Shift+I")
    window.import_csv_action.setStatusTip("Import CSV at the selected cell")
    window.import_csv_action.triggered.connect(window._import_csv)
    window.export_csv_action = QAction("Export C&SV…", window)
    window.export_csv_action.setShortcut("Ctrl+Shift+E")
    window.export_csv_action.setStatusTip("Export the selection or used cells as CSV")
    window.export_csv_action.triggered.connect(window._export_csv)

    window.quit_action = QAction("&Quit", window)
    window.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
    window.quit_action.triggered.connect(window.close)


def _build_edit_actions(window: MainWindow, style: QStyle) -> None:
    window.undo_action = window.model.undo_stack.createUndoAction(window, "&Undo")
    window.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
    window.undo_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
    window.redo_action = window.model.undo_stack.createRedoAction(window, "&Redo")
    window.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
    window.redo_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))

    window.cut_action = QAction("Cu&t", window)
    window.cut_action.setShortcut(QKeySequence.StandardKey.Cut)
    window.cut_action.triggered.connect(window._cut)
    window.copy_action = QAction("&Copy", window)
    window.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
    window.copy_action.triggered.connect(window._copy)
    window.paste_action = QAction("&Paste", window)
    window.paste_action.setShortcut(QKeySequence.StandardKey.Paste)
    window.paste_action.triggered.connect(window._paste)
    window.delete_action = QAction("Clear contents", window)
    window.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
    window.delete_action.triggered.connect(window._clear_selection)
    window.select_all_action = QAction("Select &All", window)
    window.select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
    window.select_all_action.triggered.connect(window.table.selectAll)
    window.find_replace_action = QAction("Find and &Replace…", window)
    window.find_replace_action.setShortcut(QKeySequence.StandardKey.Find)
    window.find_replace_action.triggered.connect(window._show_find_replace)


def _build_format_actions(window: MainWindow) -> None:
    window.bold_action = QAction("Bold", window)
    window.bold_action.setToolTip("Bold (Ctrl+B)")
    window.bold_action.setShortcut(QKeySequence.StandardKey.Bold)
    window.bold_action.setCheckable(True)
    window.bold_action.toggled.connect(lambda checked: window._apply_format(bold=checked))
    window.italic_action = QAction("Italic", window)
    window.italic_action.setToolTip("Italic (Ctrl+I)")
    window.italic_action.setShortcut(QKeySequence.StandardKey.Italic)
    window.italic_action.setCheckable(True)
    window.italic_action.toggled.connect(lambda checked: window._apply_format(italic=checked))

    alignment_group = QActionGroup(window)
    alignment_group.setExclusive(True)
    window.alignment_actions = {}
    for alignment, label in (
        ("left", "Align left"),
        ("center", "Center"),
        ("right", "Align right"),
    ):
        action = QAction(label, window)
        action.setToolTip(label)
        action.setCheckable(True)
        action.triggered.connect(
            lambda checked, selected=alignment: checked and window._apply_format(alignment=selected)
        )
        alignment_group.addAction(action)
        window.alignment_actions[alignment] = action
    window.alignment_actions["left"].setChecked(True)


def _build_sheet_actions(window: MainWindow) -> None:
    window.add_rows_action = QAction("Add 10 rows", window)
    window.add_rows_action.triggered.connect(lambda: window.model.add_rows(10))
    window.add_columns_action = QAction("Add 5 columns", window)
    window.add_columns_action.triggered.connect(lambda: window.model.add_columns(5))
    window.insert_rows_action = QAction("Insert rows above", window)
    window.insert_rows_action.triggered.connect(window._insert_rows)
    window.delete_rows_action = QAction("Delete selected rows", window)
    window.delete_rows_action.triggered.connect(window._delete_rows)
    window.insert_columns_action = QAction("Insert columns left", window)
    window.insert_columns_action.triggered.connect(window._insert_columns)
    window.delete_columns_action = QAction("Delete selected columns", window)
    window.delete_columns_action.triggered.connect(window._delete_columns)
    window.sort_ascending_action = QAction("Sort selection ascending", window)
    window.sort_ascending_action.triggered.connect(lambda: window._sort_selection(descending=False))
    window.sort_descending_action = QAction("Sort selection descending", window)
    window.sort_descending_action.triggered.connect(lambda: window._sort_selection(descending=True))
    window.freeze_panes_action = QAction("Freeze panes at active cell", window)
    window.freeze_panes_action.triggered.connect(window._freeze_panes)
    window.autofit_columns_action = QAction("Auto-fit columns", window)
    window.autofit_columns_action.triggered.connect(window._autofit_columns)
    window.autofit_rows_action = QAction("Auto-fit rows", window)
    window.autofit_rows_action.triggered.connect(window._autofit_rows)
    window.hide_rows_action = QAction("Hide selected rows", window)
    window.hide_rows_action.triggered.connect(window._hide_rows)
    window.hide_columns_action = QAction("Hide selected columns", window)
    window.hide_columns_action.triggered.connect(window._hide_columns)
    window.unhide_rows_action = QAction("Unhide all rows", window)
    window.unhide_rows_action.triggered.connect(window._unhide_rows)
    window.unhide_columns_action = QAction("Unhide all columns", window)
    window.unhide_columns_action.triggered.connect(window._unhide_columns)
    window.clear_filters_action = QAction("Clear filters", window)
    window.clear_filters_action.triggered.connect(window._clear_filters)


def _build_script_action(window: MainWindow, style: QStyle) -> None:
    window.script_action = QAction("Run Python script…", window)
    window.script_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
    window.script_action.setShortcut("Ctrl+Shift+P")
    window.script_action.setStatusTip("Open the embedded Python editor")
    window.script_action.triggered.connect(window._show_script_dialog)
