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


def test_error_values_propagate_to_dependent_formulas() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "=1 / 0")
    workbook.set_cell(0, 1, "=A1 + 2")

    assert workbook.value(0, 1) == "#DIV/0!"
    workbook.close()


def test_only_dependent_formula_values_are_invalidated() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cells(
        {
            (0, 0): "1",
            (0, 1): "=A1 * 2",
            (0, 2): "5",
            (0, 3): "=C1 * 2",
        }
    )
    unrelated_coordinate = (0, 3)
    cached_unrelated_value = workbook._values[unrelated_coordinate]

    workbook.set_cell(0, 0, "3")

    assert workbook.value(0, 1) == 6
    assert workbook._values[unrelated_coordinate] == cached_unrelated_value
    workbook.close()


def test_cycles_update_when_formula_dependencies_change() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "=B1")
    workbook.set_cell(0, 1, "=A1")
    assert workbook.value(0, 0) == "#CYCLE!"
    assert workbook.value(0, 1) == "#CYCLE!"

    workbook.set_cell(0, 1, "10")
    assert workbook.value(0, 0) == 10
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
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
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
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
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


def test_scripts_are_saved_with_workbook_and_recovery(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
    workbook = Workbook(":memory:")
    workbook.set_script("main", 'sheet.set("A1", "saved")')
    workbook.set_script("report", "print('report')")
    destination = tmp_path / "scripted.sheet"
    workbook.save_as(destination)

    reopened = Workbook(destination)
    assert reopened.scripts == {
        "main": 'sheet.set("A1", "saved")',
        "report": "print('report')",
    }
    reopened.close()

    workbook.delete_script("report")
    recovered = Workbook(workbook.recovery_path)
    assert recovered.scripts == {"main": 'sheet.set("A1", "saved")'}
    recovered.close()
    workbook.close()


def test_setting_a_cell_can_grow_the_workbook() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(150, 30, "outside the initial grid")

    assert workbook.rows == 151
    assert workbook.columns == 31
    assert workbook.value(150, 30) == "outside the initial grid"
    workbook.close()


def test_inserting_rows_moves_cells_formats_and_formula_references() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cells({(0, 0): "10", (0, 1): "=A1 * 2"})
    workbook.set_format(0, 0, bold=True)

    workbook.apply_grid_state(workbook.grid_after_insert_rows(0))

    assert workbook.raw_value(1, 0) == "10"
    assert workbook.raw_value(1, 1) == "=A2 * 2"
    assert workbook.value(1, 1) == 20
    assert workbook.cell_format(1, 0).bold is True
    workbook.close()


def test_deleting_referenced_row_creates_reference_error() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cells({(0, 0): "10", (1, 1): "=A1 * 2"})

    workbook.apply_grid_state(workbook.grid_after_delete_rows(0))

    assert workbook.raw_value(0, 1) == "=#REF!"
    assert workbook.value(0, 1) == "#REF!"
    workbook.close()


def test_recovery_snapshots_can_be_discovered_and_restored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "state"))
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "recover me")

    [snapshot] = Workbook.recovery_snapshots()
    restored = Workbook.from_recovery(snapshot)

    assert restored.raw_value(0, 0) == "recover me"
    assert restored.dirty is True
    restored.save_as(tmp_path / "restored.sheet")
    assert not snapshot.path.exists()
    restored.close()
    workbook.dirty = False
    workbook.close()


def test_sorting_rows_moves_formats_and_keeps_empty_values_last() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cells({(0, 0): "bravo", (0, 1): "2", (1, 0): "alpha", (1, 1): "1"})
    workbook.set_format(0, 0, bold=True)

    workbook.apply_grid_state(workbook.grid_after_sort_rows(0, 2, 0, 1, 0, descending=False))

    assert [workbook.raw_value(row, 0) for row in range(3)] == ["alpha", "bravo", ""]
    assert workbook.cell_format(1, 0).bold is True
    workbook.close()
