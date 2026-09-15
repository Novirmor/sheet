from pathlib import Path

from sheet.workbook import Workbook


def test_formulas_recalculate_when_a_cell_changes() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "10")
    workbook.set_cell(0, 1, "5")
    workbook.set_cell(0, 2, "=A1 * B1")

    assert workbook.value(0, 2) == 50
    workbook.set_cell(0, 0, "4")
    assert workbook.value(0, 2) == 20
    workbook.close()


def test_formula_functions_and_ranges() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "2")
    workbook.set_cell(1, 0, "4")
    workbook.set_cell(2, 0, "=SUM(A1:A2)")
    workbook.set_cell(3, 0, "=AVERAGE(A1:A3)")

    assert workbook.value(2, 0) == 6
    assert workbook.value(3, 0) == 4
    workbook.close()


def test_formula_errors_are_displayed() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "=1 / 0")
    workbook.set_cell(0, 1, "=B1")

    assert workbook.value(0, 0) == "#DIV/0!"
    assert workbook.value(0, 1) == "#CYCLE!"
    workbook.close()


def test_save_as_moves_workbook_to_new_database(tmp_path: Path) -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "saved")
    destination = tmp_path / "saved.sheet"

    workbook.save_as(destination)
    workbook.close()

    reopened = Workbook(destination)
    assert reopened.raw_value(0, 0) == "saved"
    reopened.close()


def test_formatting_is_saved_with_workbook(tmp_path: Path) -> None:
    destination = tmp_path / "formatted.sheet"
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "12.5")
    workbook.set_format(0, 0, bold=True, number_format="currency")
    workbook.save_as(destination)
    workbook.close()

    reopened = Workbook(destination)
    cell_format = reopened.cell_format(0, 0)
    assert cell_format.bold is True
    assert cell_format.number_format == "currency"
    reopened.close()


def test_setting_a_cell_can_grow_the_workbook() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(150, 30, "outside the initial grid")

    assert workbook.rows == 151
    assert workbook.columns == 31
    assert workbook.value(150, 30) == "outside the initial grid"
    workbook.close()
