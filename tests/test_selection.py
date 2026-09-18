from sheet.selection import CellRange, bounds, contiguous_sections


def test_bounds_returns_the_smallest_enclosing_range() -> None:
    assert bounds([(4, 3), (1, 8), (2, 1)]) == CellRange(1, 4, 1, 8)
    assert bounds([]) is None


def test_contiguous_sections_fills_gaps_between_selected_sections() -> None:
    assert contiguous_sections([4, 1, 4]) == [1, 2, 3, 4]
    assert contiguous_sections([]) == []
