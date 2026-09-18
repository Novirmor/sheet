from sheet.csv_transfer import export_coordinates, export_rows, import_cells, import_conflict_count


def test_import_cells_offsets_rows_and_columns() -> None:
    assert import_cells([["name", "amount"], ["coffee", "4"]], 2, 3) == {
        (2, 3): "name",
        (2, 4): "amount",
        (3, 3): "coffee",
        (3, 4): "4",
    }


def test_import_conflicts_only_counts_existing_destination_cells() -> None:
    assert import_conflict_count([["a", "b"]], 1, 2, {(1, 2): "old", (1, 3): ""}) == 1


def test_export_uses_multicell_selection_or_used_coordinates() -> None:
    used = {(2, 2), (3, 3)}

    assert export_coordinates({(0, 0)}, used) == used
    assert export_coordinates({(0, 0), (0, 1)}, used) == {(0, 0), (0, 1)}
    assert export_rows({(1, 1), (2, 2)}, lambda row, column: f"{row},{column}") == [
        ["1,1", "1,2"],
        ["2,1", "2,2"],
    ]
