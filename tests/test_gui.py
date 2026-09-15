import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication

from sheet.model import SpreadsheetModel
from sheet.window import MainWindow
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
