from sheet.window_document import NATIVE_FILE_FILTER


def test_native_document_filter_excludes_interchange_formats() -> None:
    assert NATIVE_FILE_FILTER == "Sheet document (*.sheet)"
