import time
from pathlib import Path

from sheet.scripting import ScriptProcess, SheetAPI
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


def test_script_process_isolated_from_workbook() -> None:
    workbook = Workbook(":memory:")
    workbook.set_cell(0, 0, "4")
    runner = ScriptProcess('sheet.set("B1", sheet.get("A1") * 2)\nprint("done")', workbook)
    runner.start()

    result = None
    deadline = time.monotonic() + 10
    while result is None and time.monotonic() < deadline:
        result = runner.poll()
        time.sleep(0.05)

    assert result is not None
    assert result.failed is False
    assert result.changes == {(0, 1): "8"}
    assert result.output == "done\n"
    assert workbook.raw_value(0, 1) == ""
    workbook.close()


def test_external_script_can_import_from_its_own_directory(tmp_path: Path) -> None:
    helper = tmp_path / "helpers.py"
    helper.write_text("def amount():\n    return 12\n")
    script = tmp_path / "report.py"
    source = 'from helpers import amount\nsheet.set("A1", amount())'
    script.write_text(source)
    workbook = Workbook(":memory:")
    runner = ScriptProcess(source, workbook, str(script))
    runner.start()

    result = None
    deadline = time.monotonic() + 10
    while result is None and time.monotonic() < deadline:
        result = runner.poll()
        time.sleep(0.05)

    assert result is not None
    assert result.failed is False
    assert result.changes == {(0, 0): "12"}
    workbook.close()
