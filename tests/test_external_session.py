import sys
import time
from pathlib import Path

import pytest

from sheet.external_session import (
    ExternalScriptProcess,
    ExternalScriptSession,
    external_bootstrap_path,
    external_code_directory,
    external_launch_ready,
)
from sheet.scripting import SessionState
from sheet.workbook import Workbook


def _wait_for_result(session: ExternalScriptSession, timeout: float = 60):
    deadline = time.monotonic() + timeout
    result = None
    while result is None and time.monotonic() < deadline:
        result = session.poll()
        if result is None:
            time.sleep(0.02)
    assert result is not None
    return result


def _wait_for_inspection(session: ExternalScriptSession, timeout: float = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.poll()
        inspections = session.take_inspections()
        if inspections:
            return inspections[-1]
        time.sleep(0.02)
    pytest.fail("external session inspection did not arrive")


def test_this_build_ships_the_external_bootstrap() -> None:
    assert external_launch_ready() is True
    assert external_bootstrap_path().is_file()
    assert (external_code_directory() / "sheet" / "external_worker.py").is_file()


def test_external_session_runs_commands_with_variables_and_cell_changes() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    workbook.set_cell(0, 0, "7")
    session = ExternalScriptSession(sys.executable)
    try:
        session.run(
            "multiplier = 3", workbook, source_id="console", source_version=1, interactive=True
        )
        first = _wait_for_result(session)

        assert first.failed is False
        assert first.changes == {}
        session.run(
            'sheet.set("B1", multiplier * sheet.get("A1"))',
            workbook,
            source_id="main",
            source_version=2,
        )
        second = _wait_for_result(session)

        assert second.failed is False
        assert second.changes == {(0, 1): "21"}
        assert second.document_id == workbook.document_id
        assert second.snapshot_revision == workbook.revision
        assert second.source_id == "main"
        assert second.source_version == 2
        assert session.state == SessionState.IDLE
    finally:
        session.stop()
        workbook.close()


def test_external_session_streams_output_and_snapshots_variables() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ExternalScriptSession(sys.executable)
    try:
        session.run(
            "value = 5\nprint('first')\nprint('second')", workbook, source_id="c", source_version=1
        )
        result = _wait_for_result(session)

        assert result.failed is False
        assert result.stdout == "first\nsecond\n"
        session.inspect_variables()
        inspection = _wait_for_inspection(session)

        names = {variable.name for variable in inspection.variables}
        assert "value" in names
        assert inspection.error == ""
    finally:
        session.stop()
        workbook.close()


def test_external_session_reports_failures_without_cell_writes() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ExternalScriptSession(sys.executable)
    try:
        session.run(
            'sheet.set("A1", 1)\nraise ValueError("broken")',
            workbook,
            source_id="main",
            source_version=1,
        )
        result = _wait_for_result(session)

        assert result.failed is True
        assert result.changes == {}
        assert result.exception is not None
        assert result.exception.type_name == "ValueError"
        assert "broken" in result.exception.message
    finally:
        session.stop()
        workbook.close()


def test_external_session_interrupt_escalates_after_the_grace_period() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ExternalScriptSession(sys.executable, interrupt_grace=0.3)
    try:
        session.run(
            "print('busy')\nwhile True:\n    pass", workbook, source_id="main", source_version=1
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            session.poll()
            if session.take_output_events():
                break
            time.sleep(0.02)
        assert session.interrupt() is True
        result = _wait_for_result(session, timeout=30)

        assert result.failed is True
        assert result.interrupted is True
        assert "interrupt" in result.output or "Interrupt" in result.output
        assert session.state in {SessionState.IDLE, SessionState.FAILED}
    finally:
        session.stop()
        workbook.close()


def test_external_session_reports_an_unexpected_exit() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ExternalScriptSession(sys.executable)
    try:
        session.run("import os\nos._exit(3)", workbook, source_id="main", source_version=1)
        result = _wait_for_result(session)

        assert result.failed is True
        assert "exited without returning a result" in result.output
        assert session.state == SessionState.FAILED
    finally:
        session.stop()
        workbook.close()


def test_external_session_restart_clears_its_namespace() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ExternalScriptSession(sys.executable)
    try:
        session.run("kept = 1", workbook, source_id="console", source_version=1, interactive=True)
        assert _wait_for_result(session).failed is False
        first_session_id = session.session_id

        session.restart()
        session.run(
            "sentinel = 2", workbook, source_id="console", source_version=2, interactive=True
        )
        assert _wait_for_result(session).failed is False

        assert session.session_id != first_session_id
        session.inspect_variables()
        inspection = _wait_for_inspection(session)
        assert "kept" not in {variable.name for variable in inspection.variables}
    finally:
        session.stop()
        workbook.close()


def test_external_session_reports_a_missing_interpreter_without_spawning() -> None:
    session = ExternalScriptSession(Path("/nonexistent/python-for-sheet-tests"))
    session.start()

    assert session.state == SessionState.FAILED
    result = session.poll()

    assert result is not None
    assert result.failed is True
    assert "Could not start" in result.output
    session.stop()


def test_fresh_external_process_runs_once_and_stops() -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    workbook.set_cell(0, 0, "4")
    runner = ExternalScriptProcess(
        sys.executable, 'sheet.set("B1", sheet.get("A1") * 2)\nprint("done")', workbook
    )
    runner.start()

    result = None
    deadline = time.monotonic() + 60
    while result is None and time.monotonic() < deadline:
        result = runner.poll()
        if result is None:
            time.sleep(0.02)

    assert result is not None
    assert result.failed is False
    assert result.changes == {(0, 1): "8"}
    assert result.output == "done\n"
    assert runner.running is False
    workbook.close()
