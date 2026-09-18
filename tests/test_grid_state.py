import pytest

from sheet.grid_state import GridState, delete_columns, insert_rows, sort_rows


def test_insert_rows_moves_cells_and_formula_references() -> None:
    state = GridState(3, 2, {(1, 0): "=A1", (2, 1): "value"}, {})

    assert insert_rows(state, 1) == GridState(4, 2, {(2, 0): "=A1", (3, 1): "value"}, {})


def test_delete_columns_replaces_deleted_formula_references() -> None:
    state = GridState(2, 3, {(0, 2): "=B1"}, {})

    assert delete_columns(state, 1).cells == {(0, 1): "=#REF!"}


def test_sort_rows_keeps_empty_rows_last() -> None:
    state = GridState(3, 1, {(0, 0): "bravo", (1, 0): "alpha"}, {})

    updated = sort_rows(
        state, 0, 2, 0, 0, 0, False, lambda row, column: (1, state.cells[(row, column)])
    )

    assert updated.cells == {(0, 0): "alpha", (1, 0): "bravo"}


def test_grid_transforms_validate_dimensions() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        delete_columns(GridState(1, 1, {}, {}), 0)
