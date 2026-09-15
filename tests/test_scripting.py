from sheet.scripting import SheetAPI
from sheet.workbook import Workbook


def test_script_api_reads_and_writes_cells() -> None:
    workbook = Workbook(":memory:")
    sheet = SheetAPI(workbook)
    sheet.set("A1", 10)
    sheet.set("B1", "=A1 * 2")

    assert sheet.get("B1") == 20
    assert sheet.raw("B1") == "=A1 * 2"
    workbook.close()


def test_script_api_reads_and_writes_ranges() -> None:
    workbook = Workbook(":memory:")
    sheet = SheetAPI(workbook)
    sheet.write("B2", [[1, 2], [3, 4]])

    assert sheet.range("B2:C3") == [[1, 2], [3, 4]]
    sheet.clear("B2:C3")
    assert sheet.range("B2:C3") == [[None, None], [None, None]]
    workbook.close()
