from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelection, QItemSelectionModel, QRect
from PySide6.QtWidgets import QApplication, QDockWidget, QLineEdit, QStyleOptionViewItem, QToolBar

from sheet.code_editor import CodeEditor, LineNumberArea, PythonHighlighter
from sheet.csv_io import CsvData
from sheet.model import SpreadsheetModel
from sheet.script_dialog import ScriptWorkspace
from sheet.script_library import ScriptLibraryPanel
from sheet.script_source import ScriptSourcePanel
from sheet.window import NATIVE_FILE_FILTER, CellEditorDelegate, MainWindow
from sheet.workbook import Workbook


@pytest.fixture(scope="module")
def application() -> QApplication:
    instance = QApplication.instance()
    return instance if isinstance(instance, QApplication) else QApplication([])


def test_cell_edits_can_be_undone(application: QApplication) -> None:
    model = SpreadsheetModel(Workbook(":memory:"))
    index = model.index(0, 0)

    assert model.setData(index, "42") is True
    assert model.workbook.value(0, 0) == 42

    model.undo_stack.undo()
    assert model.workbook.value(0, 0) is None

    model.undo_stack.redo()
    assert model.workbook.value(0, 0) == 42
    model.workbook.close()


def test_open_dialog_only_advertises_native_documents() -> None:
    assert NATIVE_FILE_FILTER == "Sheet document (*.sheet)"
    assert ".xlsx" not in NATIVE_FILE_FILTER
    assert ".xls" not in NATIVE_FILE_FILTER
    assert ".csv" not in NATIVE_FILE_FILTER


def test_cell_editor_uses_the_full_item_rectangle(application: QApplication) -> None:
    delegate = CellEditorDelegate()
    editor = QLineEdit()
    option = QStyleOptionViewItem()
    option.rect = QRect(10, 20, 112, 27)
    model = SpreadsheetModel(Workbook(":memory:"))

    delegate.updateEditorGeometry(editor, option, model.index(0, 0))

    assert editor.geometry() == option.rect
    model.workbook.close()


def test_code_editor_keeps_line_numbers_and_highlighting(application: QApplication) -> None:
    editor = CodeEditor("print('hello')")
    highlighter = PythonHighlighter(editor)

    assert isinstance(editor.line_number_area, LineNumberArea)
    assert editor.line_number_width() > 0
    assert highlighter.document() is editor.document()


def test_fx_menu_and_mouse_selection_insert_formula_ranges(application: QApplication) -> None:
    window = MainWindow(":memory:")

    assert [action.text() for action in window.fx_button.menu().actions()] == [
        "Math",
        "Text",
        "Logic",
    ]
    window._insert_function("SUM")
    selection = window.table.selectionModel()
    selection.select(window.model.index(0, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    selection.select(window.model.index(1, 1), QItemSelectionModel.SelectionFlag.Select)
    window._selection_changed(QItemSelection(), QItemSelection())

    assert window.formula_bar.text() == "=SUM(A1:B2)"
    window.close()


def test_window_builds_expected_menus_and_toolbars(application: QApplication) -> None:
    window = MainWindow(":memory:")

    assert [action.text() for action in window.menuBar().actions()] == [
        "&File",
        "&Edit",
        "F&ormat",
        "&Sheet",
        "&Python",
        "&View",
    ]
    assert {toolbar.objectName() for toolbar in window.findChildren(QToolBar)} == {
        "mainToolbar",
        "formatToolbar",
    }
    window.close()


def test_bulk_edits_and_formatting_can_be_undone(application: QApplication) -> None:
    model = SpreadsheetModel(Workbook(":memory:"))
    model.set_cells({(0, 0): "1", (0, 1): "2"}, "Paste cells")
    model.apply_format([model.index(0, 0), model.index(0, 1)], bold=True)

    assert model.workbook.cell_format(0, 0).bold is True
    model.undo_stack.undo()
    assert model.workbook.cell_format(0, 0).bold is False
    model.undo_stack.undo()
    assert model.workbook.value(0, 0) is None
    assert model.workbook.value(0, 1) is None
    model.workbook.close()


def test_dimension_changes_can_be_undone(application: QApplication) -> None:
    model = SpreadsheetModel(Workbook(":memory:"))
    initial = (model.workbook.rows, model.workbook.columns)
    model.add_rows(10)
    model.add_columns(5)

    assert (model.workbook.rows, model.workbook.columns) == (110, 31)
    model.undo_stack.undo()
    model.undo_stack.undo()
    assert (model.workbook.rows, model.workbook.columns) == initial
    model.workbook.close()


def test_inserted_rows_can_be_undone(application: QApplication) -> None:
    model = SpreadsheetModel(Workbook(":memory:"))
    model.set_cells({(0, 0): "value"})
    model.insert_rows(0)

    assert model.workbook.raw_value(1, 0) == "value"
    model.undo_stack.undo()
    assert model.workbook.raw_value(0, 0) == "value"
    model.workbook.close()


def test_sorted_rows_can_be_undone(application: QApplication) -> None:
    model = SpreadsheetModel(Workbook(":memory:"))
    model.set_cells({(0, 0): "bravo", (1, 0): "alpha"})
    model.sort_rows(0, 1, 0, 0, 0, descending=False)

    assert [model.workbook.raw_value(row, 0) for row in range(2)] == ["alpha", "bravo"]
    model.undo_stack.undo()
    assert [model.workbook.raw_value(row, 0) for row in range(2)] == ["bravo", "alpha"]
    model.workbook.close()


def test_script_changes_are_one_undoable_action(application: QApplication) -> None:
    model = SpreadsheetModel(Workbook(":memory:"))
    model.apply_script_changes({(101, 26): "42"}, 102, 27)

    assert model.undo_stack.count() == 1
    assert model.workbook.raw_value(101, 26) == "42"
    model.undo_stack.undo()
    assert (model.workbook.rows, model.workbook.columns) == (100, 26)
    assert model.workbook.raw_value(101, 26) == ""
    model.workbook.close()


def test_script_workspace_switches_and_saves_named_scripts(
    application: QApplication, tmp_path: Path
) -> None:
    workbook = Workbook(":memory:")
    workbook.set_script("main", "print('main')")
    workbook.set_script("report", "print('report')")
    workspace = ScriptWorkspace(SpreadsheetModel(workbook))

    assert workspace.active_name == "main"
    workspace.script_list.setCurrentRow(1)
    assert workspace.active_name == "report"
    workspace.editor.setPlainText("print('updated')")
    workspace.sync_active_script()
    assert workbook.scripts["report"] == "print('updated')"
    external_path = tmp_path / "report.py"
    workspace.external_paths["report"] = external_path
    workspace._save_external_script()
    assert external_path.read_text() == "print('updated')"
    workspace.deleteLater()
    workbook.close()


def test_script_workspace_cannot_float_or_close(application: QApplication) -> None:
    workspace = ScriptWorkspace(SpreadsheetModel(Workbook(":memory:")))

    assert workspace.features() == QDockWidget.DockWidgetFeature.DockWidgetMovable
    assert isinstance(workspace.library, ScriptLibraryPanel)
    assert isinstance(workspace.source_panel, ScriptSourcePanel)
    workspace.model.workbook.close()


def test_script_workspace_reports_syntax_errors_before_starting(application: QApplication) -> None:
    workspace = ScriptWorkspace(SpreadsheetModel(Workbook(":memory:")))
    workspace.editor.setPlainText("def broken(:\n    pass")
    workspace.run_script()

    assert workspace.runner is None
    assert workspace.output.toPlainText().startswith("Syntax error at line 1, column 12")
    workspace.model.workbook.close()


def test_window_copy_and_paste(application: QApplication) -> None:
    window = MainWindow(":memory:")
    window.model.set_cells({(0, 0): "alpha", (0, 1): "beta"})
    selection = window.table.selectionModel()
    selection.select(window.model.index(0, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    selection.select(window.model.index(0, 1), QItemSelectionModel.SelectionFlag.Select)
    window._copy()

    window.table.setCurrentIndex(window.model.index(1, 0))
    window._paste()
    assert window.workbook.raw_value(1, 0) == "alpha"
    assert window.workbook.raw_value(1, 1) == "beta"

    window.workbook.dirty = False
    window.close()


def test_csv_export_uses_used_cells_or_multicell_selection(application: QApplication) -> None:
    window = MainWindow(":memory:")
    window.model.set_cells({(0, 0): "name", (1, 1): "=A1"})

    assert window._csv_rows() == [["name", ""], ["", "=A1"]]

    selection = window.table.selectionModel()
    selection.select(window.model.index(0, 0), QItemSelectionModel.SelectionFlag.ClearAndSelect)
    selection.select(window.model.index(0, 1), QItemSelectionModel.SelectionFlag.Select)
    assert window._csv_rows() == [["name", ""]]

    window.workbook.dirty = False
    window.close()


def test_csv_can_export_calculated_values_and_detect_import_conflicts(
    application: QApplication,
) -> None:
    window = MainWindow(":memory:")
    window.model.set_cells({(0, 0): "2", (0, 1): "=A1 * 3"})

    assert window._csv_rows(display_values=True) == [["2", "6"]]
    assert window._csv_conflicts(CsvData([["new", "values"]], ",", "utf-8"), 0, 0) == 2
    window.workbook.dirty = False
    window.close()


def test_find_and_replace_navigates_cells_and_uses_one_undo(application: QApplication) -> None:
    window = MainWindow(":memory:")
    window.model.set_cells({(0, 0): "Coffee", (0, 1): "coffee shop", (1, 0): "Tea"})
    window.table.setCurrentIndex(window.model.index(0, 0))

    assert window._find_next("coffee", match_case=False) is True
    assert window.table.currentIndex() == window.model.index(0, 1)
    assert window._replace_all("coffee", "tea", match_case=False) == 2
    assert window.workbook.raw_value(0, 0) == "tea"
    assert window.workbook.raw_value(0, 1) == "tea shop"

    window.model.undo_stack.undo()
    assert window.workbook.raw_value(0, 0) == "Coffee"
    assert window.workbook.raw_value(0, 1) == "coffee shop"
    window.workbook.dirty = False
    window.close()


def test_header_selection_selects_complete_rows_and_columns(application: QApplication) -> None:
    window = MainWindow(":memory:")
    window._select_row(2)
    assert len(window.table.selectionModel().selectedIndexes()) == window.workbook.columns

    window._select_column(3)
    assert len(window.table.selectionModel().selectedIndexes()) == window.workbook.rows
    window.close()
