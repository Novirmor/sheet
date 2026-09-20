import time
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from sheet.script_api import api_member_names
from sheet.script_documents import available_name
from sheet.scripting import ScriptProcess, ScriptSession, SessionState, SheetAPI
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


def test_script_api_validates_entire_table_before_writing() -> None:
    workbook = Workbook(":memory:")
    sheet = SheetAPI(workbook)
    sheet.set("A1", "existing")

    with pytest.raises(ValueError, match="rectangular"):
        sheet.write("A1", [["valid"], ["invalid", "row"]])
    with pytest.raises(TypeError, match="unsupported"):
        sheet.write("A1", [["valid", object()]])

    assert sheet.range("A1:B2") == [["existing", None], [None, None]]
    sheet.write("A1", [[date(2026, 1, 2), float("nan")]])
    assert sheet.range("A1:B1") == [["2026-01-02", None]]
    workbook.close()


def test_dataframe_write_handles_index_without_a_header() -> None:
    workbook = Workbook(":memory:")
    sheet = SheetAPI(workbook)
    frame = pd.DataFrame({"amount": [4, 5]}, index=["coffee", "tea"])

    sheet.write_dataframe("A1", frame, include_header=False, include_index=True)

    assert sheet.range("A1:B2") == [["coffee", 4], ["tea", 5]]
    assert "write_dataframe" in api_member_names()
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
    assert result.document_id == workbook.document_id
    assert result.snapshot_revision == workbook.revision
    assert result.run_id
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


def test_script_process_exposes_pandas_and_plotly_helpers() -> None:
    workbook = Workbook(":memory:")
    source = """frame = pd.DataFrame([[\"Coffee\", 4.5]], columns=[\"Item\", \"Amount\"])
sheet.write_dataframe(\"A1\", frame)
print(px.bar(frame, x=\"Item\", y=\"Amount\").__class__.__name__)
"""
    runner = ScriptProcess(source, workbook)
    runner.start()

    result = None
    deadline = time.monotonic() + 15
    while result is None and time.monotonic() < deadline:
        result = runner.poll()
        time.sleep(0.05)

    assert result is not None
    assert result.failed is False
    assert result.changes == {(0, 0): "Item", (0, 1): "Amount", (1, 0): "Coffee", (1, 1): "4.5"}
    assert result.output == "Figure\n"
    workbook.close()


def test_script_process_reports_an_unexpected_child_exit() -> None:
    workbook = Workbook(":memory:")
    runner = ScriptProcess("import os\nos._exit(1)", workbook)
    runner.start()

    result = None
    deadline = time.monotonic() + 10
    while result is None and time.monotonic() < deadline:
        result = runner.poll()
        time.sleep(0.05)

    assert result is not None
    assert result.failed is True
    assert "without returning" in result.output
    workbook.close()


def _wait_for_session_result(session: ScriptSession, timeout: float = 10):
    deadline = time.monotonic() + timeout
    result = None
    while result is None and time.monotonic() < deadline:
        result = session.poll()
        time.sleep(0.02)
    assert result is not None
    return result


def _wait_for_inspection(session: ScriptSession, timeout: float = 10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.poll()
        inspections = session.take_inspections()
        if inspections:
            return inspections[-1]
        time.sleep(0.02)
    pytest.fail("session inspection did not arrive")


def test_script_session_preserves_variables_and_rebinds_a_fresh_sheet_snapshot() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run("multiplier = 3", workbook, source_id="console", source_version=1, interactive=True)
    first = _wait_for_session_result(session)

    assert first.failed is False
    workbook.set_cell(0, 0, "7")
    session.run(
        'sheet.set("B1", multiplier * sheet.get("A1"))',
        workbook,
        source_id="main",
        source_version=2,
    )
    second = _wait_for_session_result(session)

    assert second.failed is False
    assert second.changes == {(0, 1): "21"}
    assert second.session_id == session.session_id
    assert second.source_id == "main"
    assert second.source_version == 2
    session.stop()
    workbook.close()


def test_script_session_failed_commands_discard_cell_writes_but_keep_python_variables() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run(
        'answer = 9\nsheet.set("A1", answer)\nraise RuntimeError("broken")',
        workbook,
        source_id="console",
        source_version=1,
        interactive=True,
    )
    failed = _wait_for_session_result(session)

    assert failed.failed is True
    assert failed.changes == {}
    session.run("answer", workbook, source_id="console", source_version=2, interactive=True)
    preserved = _wait_for_session_result(session)

    assert preserved.output == "9\n"
    session.stop()
    workbook.close()


def test_script_session_restart_clears_its_namespace() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run("saved = 1", workbook, source_id="console", source_version=1, interactive=True)
    _wait_for_session_result(session)
    previous_id = session.session_id
    session.restart()
    session.run("saved", workbook, source_id="console", source_version=2, interactive=True)
    result = _wait_for_session_result(session)

    assert session.session_id != previous_id
    assert result.failed is True
    assert "NameError" in result.output
    session.stop()
    workbook.close()


def test_fresh_script_process_does_not_change_session_variables() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run("saved = 5", workbook, source_id="console", source_version=1, interactive=True)
    _wait_for_session_result(session)
    fresh = ScriptProcess("saved = 99", workbook)
    fresh.start()

    result = None
    deadline = time.monotonic() + 10
    while result is None and time.monotonic() < deadline:
        result = fresh.poll()
        time.sleep(0.02)

    assert result is not None
    assert result.failed is False
    session.run("saved", workbook, source_id="console", source_version=2, interactive=True)
    preserved = _wait_for_session_result(session)
    assert preserved.output == "5\n"
    session.stop()
    workbook.close()


def test_script_session_interrupts_a_running_command() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession(interrupt_grace=1)
    session.run("while True:\n    pass", workbook, source_id="console", source_version=1)
    time.sleep(0.2)

    assert session.interrupt() is True
    result = _wait_for_session_result(session)

    assert result.failed is True
    assert result.interrupted is True
    assert session.state == SessionState.IDLE
    session.stop()
    workbook.close()


def test_script_session_timeout_terminates_the_worker_and_reports_variable_loss() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run(
        "import time\ntime.sleep(10)",
        workbook,
        source_id="console",
        source_version=1,
        timeout=0.1,
    )
    result = _wait_for_session_result(session)

    assert result.failed is True
    assert "timed out" in result.output
    assert "variables were lost" in result.output
    assert session.state == SessionState.FAILED
    workbook.close()


def test_script_session_reports_an_unexpected_child_exit() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run("import os\nos._exit(1)", workbook, source_id="console", source_version=1)
    result = _wait_for_session_result(session)

    assert result.failed is True
    assert "without returning" in result.output
    assert session.state == SessionState.FAILED
    workbook.close()


def test_script_session_returns_structured_streams_exception_and_display_results() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run(
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\n"
        "display(pd.DataFrame({'amount': [4, None]}))\nraise ValueError('bad value')",
        workbook,
        source_id="main",
        source_version=7,
    )
    result = _wait_for_session_result(session)

    assert result.failed is True
    assert result.stdout == "out\n"
    assert "err\n" in result.stderr
    assert result.exception is not None
    assert result.exception.type_name == "ValueError"
    assert result.exception.frames[-1].source_id == "main"
    assert result.exception.frames[-1].source_version == 7
    assert result.displays[0].kind == "table"
    assert result.displays[0].columns == ("amount",)
    assert result.displays[0].rows == (("4.0",), ("nan",))
    session.stop()
    workbook.close()


def test_script_session_streams_ordered_output_before_completion() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    run_id = session.run(
        "import sys, time\nprint('first')\nprint('second', file=sys.stderr)\ntime.sleep(0.4)",
        workbook,
        source_id="console",
        source_version=1,
    )
    events = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not events:
        assert session.poll() is None
        events.extend(session.take_output_events())
        time.sleep(0.02)

    assert [(event.channel, event.text) for event in events] == [
        ("stdout", "first"),
        ("stdout", "\n"),
        ("stderr", "second"),
        ("stderr", "\n"),
    ]
    assert [event.sequence for event in events] == sorted(event.sequence for event in events)
    assert {event.run_id for event in events} == {run_id}
    assert _wait_for_session_result(session).failed is False
    session.stop()
    workbook.close()


def test_variable_inspection_is_bounded_and_stale_handles_are_rejected() -> None:
    workbook = Workbook(":memory:")
    session = ScriptSession()
    session.run(
        "class Noisy:\n    def __repr__(self):\n        raise RuntimeError('repr called')\n"
        "noisy = Noisy()\nframe = pd.DataFrame({'a': range(250), 'b': [None] * 250})",
        workbook,
        source_id="console",
        source_version=1,
    )
    assert _wait_for_session_result(session).failed is False
    session.inspect_variables()
    snapshot = _wait_for_inspection(session)
    by_name = {variable.name: variable for variable in snapshot.variables}

    assert by_name["noisy"].summary == "<Noisy>"
    assert by_name["frame"].rows == 250
    assert by_name["frame"].columns == 2
    session.inspect_variable_page(by_name["frame"].handle, 100)
    page = _wait_for_inspection(session).page
    assert page is not None
    assert page.start == 100
    assert len(page.rows) == 100
    assert page.partial is True
    assert page.missing == (0, 100)
    assert page.sheet_rows[0] == ("100", "")

    session.run("frame = 1", workbook, source_id="console", source_version=2)
    assert _wait_for_session_result(session).failed is False
    session.inspect_variable_page(by_name["frame"].handle, 0)
    assert "no longer" in _wait_for_inspection(session).error
    session.stop()
    workbook.close()


def test_script_names_receive_a_simple_numeric_suffix() -> None:
    assert available_name("report", {"report", "report 2"}) == "report 3"
