from pathlib import Path

from sheet.database import SpreadsheetStore
from sheet.formatting import CellFormat


def test_cells_and_dimensions_are_persistent(tmp_path: Path) -> None:
    path = tmp_path / "workbook.sheet"
    store = SpreadsheetStore(path)
    store.set_cell(0, 0, "hello")
    store.set_cell(1, 2, "=A1")
    store.set_dimensions(200, 40)
    store.close()

    reopened = SpreadsheetStore(path)
    assert reopened.load_cells() == {(0, 0): "hello", (1, 2): "=A1"}
    assert reopened.dimensions() == (200, 40)
    reopened.close()


def test_empty_value_deletes_cell() -> None:
    store = SpreadsheetStore(":memory:")
    store.set_cell(0, 0, "value")
    store.set_cell(0, 0, "")
    assert store.load_cells() == {}
    store.close()


def test_cell_format_is_persistent() -> None:
    store = SpreadsheetStore(":memory:")
    expected = CellFormat(bold=True, alignment="center", number_format="currency")
    store.set_format(2, 3, expected)

    assert store.load_formats() == {(2, 3): expected}
    store.close()


def test_scripts_are_persistent() -> None:
    store = SpreadsheetStore(":memory:")
    store.replace_scripts((("main", "print('main')"), ("report", "print('report')")))

    assert store.load_scripts() == {"main": "print('main')", "report": "print('report')"}
    store.close()
