from sheet.clipboard import copy_text, paste_rows


def test_copy_text_preserves_rectangles_and_sanitizes_multiline_values() -> None:
    values = {(0, 0): "first", (1, 1): "second\nline"}

    assert copy_text(values, lambda row, column: values[(row, column)]) == "first\t\n\tsecond line"


def test_paste_rows_handles_tabs_and_a_single_empty_cell() -> None:
    assert paste_rows("first\tsecond\nthird") == [["first", "second"], ["third"]]
    assert paste_rows("") == [[""]]
