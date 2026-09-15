import pytest

from sheet.coordinates import cell_reference, cells_in_range, column_index, column_name


@pytest.mark.parametrize(
    ("index", "name"),
    [(0, "A"), (25, "Z"), (26, "AA"), (51, "AZ"), (701, "ZZ")],
)
def test_column_names_round_trip(index: int, name: str) -> None:
    assert column_name(index) == name
    assert column_index(name) == index


def test_cell_reference() -> None:
    assert cell_reference(0, 0) == "A1"
    assert cell_reference(9, 27) == "AB10"


def test_range_can_be_reversed() -> None:
    assert list(cells_in_range("B2", "A1")) == [(0, 0), (0, 1), (1, 0), (1, 1)]
