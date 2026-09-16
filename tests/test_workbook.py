from pathlib import Path

import pytest

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


def test_saved_workbook_changes_are_not_written_until_save(tmp_path: Path) -> None:
    destination = tmp_path / "saved.sheet"
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "original")
    workbook.save_as(destination)
    workbook.set_cell(0, 0, "unsaved")

    on_disk = Workbook(destination)
    assert on_disk.raw_value(0, 0) == "original"
    on_disk.close()

    workbook.save()
    saved = Workbook(destination)
    assert saved.raw_value(0, 0) == "unsaved"
    saved.close()
    workbook.close()


def test_save_as_failure_leaves_existing_file_untouched(tmp_path: Path) -> None:
    destination = tmp_path / "saved.sheet"
    original = Workbook(":memory:")
    original.set_cell(0, 0, "original")
    original.save_as(destination)
    original.close()

    workbook = Workbook(destination)
    workbook.set_cell(0, 0, "changed")
    invalid_parent = tmp_path / "not-a-directory"
    invalid_parent.write_text("file")
    invalid_destination = invalid_parent / "saved.sheet"
    with pytest.raises(OSError):
        workbook.save_as(invalid_destination)

    existing = Workbook(destination)
    assert existing.raw_value(0, 0) == "original"
    existing.close()
    workbook.close()


def test_recovery_snapshot_tracks_unsaved_work(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "recover me")

    assert workbook.recovery_path.exists()
    recovered = Workbook(workbook.recovery_path)
    assert recovered.raw_value(0, 0) == "recover me"
    recovered.close()

    workbook.save_as(tmp_path / "saved.sheet")
    assert not workbook.recovery_path.exists()
    workbook.close()


def test_discarding_changes_removes_recovery_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "discard me")
    assert workbook.recovery_path.exists()

    workbook.discard_changes()
    workbook.close()
    assert not workbook.recovery_path.exists()


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
