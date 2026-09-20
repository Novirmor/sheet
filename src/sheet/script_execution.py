from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from sheet.external_session import ExternalScriptProcess, ExternalScriptSession
from sheet.scripting import ScriptProcess, ScriptResult, ScriptSession, SessionResult, SessionState

MAX_CONSOLE_HISTORY = 100

if TYPE_CHECKING:
    from sheet.script_dialog import ScriptWorkspace


def run_script(workspace: ScriptWorkspace) -> None:
    if _is_busy(workspace):
        return
    workspace.sync_active_script()
    source = workspace.editor.toPlainText()
    _run_session_script(workspace, source, "Running script in session...")


def run_selection(workspace: ScriptWorkspace) -> None:
    if _is_busy(workspace):
        return
    workspace.sync_active_script()
    source = workspace.editor.textCursor().selectedText().replace("\u2029", "\n")
    if not source:
        workspace.output.setPlainText("Select script text to run.")
        return
    _run_session_script(workspace, source, "Running selected script text in session...")


def _ensure_session(workspace: ScriptWorkspace) -> ScriptSession | ExternalScriptSession:
    session = workspace.session
    if session is None:
        interpreter = workspace.external_interpreter()
        session = ExternalScriptSession(interpreter) if interpreter is not None else ScriptSession()
        workspace.session = session
    return session


def _run_session_script(workspace: ScriptWorkspace, source: str, status: str) -> None:
    try:
        ast.parse(source)
    except SyntaxError as error:
        line = error.lineno or 1
        column = error.offset or 1
        workspace.output.setPlainText(f"Syntax error at line {line}, column {column}: {error.msg}")
        workspace._go_to_line(line, column)
        return
    session = _ensure_session(workspace)
    path = workspace.external_paths.get(workspace.active_name)
    workspace.begin_run(source, workspace.active_name, workspace.source_version)
    workspace.session_run_id = session.run(
        source,
        workspace.model.workbook,
        source_id=workspace.active_name,
        source_version=workspace.source_version,
        script_path=str(path) if path else None,
    )
    workspace.output.setPlainText(status)
    workspace.timer.start()
    set_running(workspace, True)


def fresh_run_script(workspace: ScriptWorkspace) -> None:
    if _is_busy(workspace):
        return
    workspace.sync_active_script()
    source = workspace.editor.toPlainText()
    try:
        ast.parse(source)
    except SyntaxError as error:
        line = error.lineno or 1
        column = error.offset or 1
        workspace.output.setPlainText(f"Syntax error at line {line}, column {column}: {error.msg}")
        workspace._go_to_line(line, column)
        return
    workspace.output.setPlainText("Running fresh script…")
    path = workspace.external_paths.get(workspace.active_name)
    workspace.begin_run(source, workspace.active_name, workspace.source_version)
    interpreter = workspace.external_interpreter()
    if interpreter is not None:
        runner: ScriptProcess | ExternalScriptProcess = ExternalScriptProcess(
            interpreter,
            source,
            workspace.model.workbook,
            str(path) if path else None,
            source_id=workspace.active_name,
            source_version=workspace.source_version,
        )
    else:
        runner = ScriptProcess(
            source,
            workspace.model.workbook,
            str(path) if path else None,
            source_id=workspace.active_name,
            source_version=workspace.source_version,
        )
    workspace.runner = runner
    runner.start()
    workspace.timer.start()
    set_running(workspace, True)


def run_console(workspace: ScriptWorkspace) -> None:
    if _is_busy(workspace):
        return
    source = workspace.console_input.toPlainText()
    if not source.strip():
        return
    session = _ensure_session(workspace)
    workspace.console_version += 1
    workspace.console_history.append(source)
    del workspace.console_history[:-MAX_CONSOLE_HISTORY]
    workspace.console_history_index = len(workspace.console_history)
    workspace.console_input.clear()
    workspace.begin_run(source, "console", workspace.console_version)
    workspace.session_run_id = session.run(
        source,
        workspace.model.workbook,
        source_id="console",
        source_version=workspace.console_version,
        interactive=True,
    )
    workspace.output.setPlainText(f">>> {source}\nRunning console command...")
    workspace.timer.start()
    set_running(workspace, True)


def interrupt_session(workspace: ScriptWorkspace) -> None:
    if workspace.runner is not None:
        workspace.runner.stop()
        workspace.runner = None
        workspace.output.appendPlainText("\nFresh script stopped.")
        set_running(workspace, False)
        return
    if workspace.session is not None and workspace.session.interrupt():
        workspace.output.appendPlainText("\nInterrupting session...")
        set_running(workspace, True)


def restart_session(workspace: ScriptWorkspace) -> None:
    if _is_busy(workspace):
        return
    session = _ensure_session(workspace)
    session.restart()
    workspace.session_run_id = ""
    workspace.timer.start()
    workspace.output.setPlainText("Session restarted. Python variables were cleared.")
    set_running(workspace, False)


def stop_script(workspace: ScriptWorkspace) -> None:
    if workspace.runner is not None:
        workspace.runner.stop()
        workspace.runner = None
    if workspace.session is not None:
        workspace.session.stop()
        workspace.session = None
    workspace.session_run_id = ""
    workspace.timer.stop()
    set_running(workspace, False)


def poll_runner(workspace: ScriptWorkspace) -> None:
    if workspace.runner is not None:
        result = workspace.runner.poll()
        if result is not None:
            workspace.runner = None
            set_running(workspace, False)
            finish_script(workspace, result)
            if workspace.session is None:
                workspace.timer.stop()
    if workspace.session is not None:
        result = workspace.session.poll()
        for event in workspace.session.take_output_events():
            if event.run_id == workspace.session_run_id:
                workspace.append_output(event.channel, event.text)
        for inspection in workspace.session.take_inspections():
            workspace.apply_inspection(inspection)
        if result is not None:
            if result.run_id == workspace.session_run_id:
                workspace.session_run_id = ""
                set_running(workspace, False)
                finish_session(workspace, result)
            elif result.run_id == "":
                workspace.output.appendPlainText(f"\n{result.output}")
                set_running(workspace, False)
            if workspace.session.state == SessionState.FAILED:
                workspace.timer.stop()


def finish_script(workspace: ScriptWorkspace, result: ScriptResult | SessionResult) -> None:
    output = result.output.rstrip()
    fallback = "Script failed." if result.failed else "Script finished."
    workspace.output.setPlainText(output or fallback)
    workspace.present_result(
        stdout=result.stdout,
        stderr=result.stderr,
        exception=result.exception,
        displays=result.displays,
        duration_ms=result.duration_ms,
    )
    if result.failed:
        _go_to_script_error(workspace, result.output, result.exception)
        return
    _apply_changes(workspace, result)


def finish_session(workspace: ScriptWorkspace, result: SessionResult) -> None:
    output = result.output.rstrip()
    fallback = "Command failed." if result.failed else "Command finished."
    if not result.stdout and not result.stderr:
        workspace.output.setPlainText(output or fallback)
    workspace.present_result(
        stdout=result.stdout,
        stderr=result.stderr,
        exception=result.exception,
        displays=result.displays,
        duration_ms=result.duration_ms,
    )
    if result.failed:
        if result.source_id != "console":
            _go_to_script_error(workspace, result.output, result.exception)
        workspace.output.appendPlainText(
            "\nCell writes were not applied. Python variables and external side effects may have "
            "changed."
        )
        workspace._request_variable_snapshot()
        return
    if (
        result.source_id == workspace.active_name
        and result.source_version != workspace.source_version
    ):
        workspace.output.appendPlainText(
            "\nScript source changed while it ran; its changes were not applied."
        )
        workspace._request_variable_snapshot()
        return
    _apply_changes(workspace, result)
    workspace._request_variable_snapshot()


def _apply_changes(workspace: ScriptWorkspace, result: ScriptResult | SessionResult) -> None:
    workbook = workspace.model.workbook
    if result.document_id != workbook.document_id or result.snapshot_revision != workbook.revision:
        workspace.output.appendPlainText(
            "\nWorkbook changed while the command ran. Its changes were not applied; run it again."
        )
        return
    workspace.model.apply_script_changes(result.changes, result.rows, result.columns)
    workspace.output.appendPlainText(
        f"\nApplied {len(result.changes)} cell change(s) as one undoable action."
    )


def _go_to_script_error(workspace: ScriptWorkspace, output: str, exception=None) -> None:
    if exception is not None:
        frames = [frame for frame in exception.frames if frame.source_id == workspace.active_name]
        if frames:
            frame = frames[-1]
            if frame.source_version == workspace.source_version:
                workspace._go_to_line(frame.line)
            else:
                workspace.output.appendPlainText(
                    "\nTraceback source is stale; navigation was skipped."
                )
            return
        workspace.output.appendPlainText(
            "\nTraceback source is not the active editor; navigation was skipped."
        )
        return
    matches = re.findall(r'File "(?:<sheet-[^>]+>|[^\"]+)", line (\d+)', output)
    if matches:
        workspace._go_to_line(int(matches[-1]))


def _is_busy(workspace: ScriptWorkspace) -> bool:
    return workspace.runner is not None or (
        workspace.session is not None and workspace.session.running
    )


def set_running(workspace: ScriptWorkspace, running: bool) -> None:
    workspace.run_button.setEnabled(not running)
    workspace.fresh_run_button.setEnabled(not running)
    workspace.selection_run_button.setEnabled(not running)
    workspace.console_run_button.setEnabled(not running)
    workspace.restart_button.setEnabled(not running)
    workspace.interrupt_button.setEnabled(running)
    workspace.library.set_running(running, workspace.active_name in workspace.external_paths)
    workspace.editor.setReadOnly(running)
    workspace.console_input.setReadOnly(running)
    workspace.variable_explorer.set_running(running)


def run_captured(workspace: ScriptWorkspace, entry) -> None:
    if _is_busy(workspace):
        return
    if entry.source_id == workspace.active_name and workspace.editor.toPlainText() != entry.source:
        workspace.output.setPlainText(
            "Editor differs from the captured run; rerunning captured source."
        )
    _run_session_script(
        workspace, entry.source, "Rerunning captured source with a fresh sheet snapshot..."
    )
