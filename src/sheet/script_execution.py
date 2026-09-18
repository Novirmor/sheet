from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from sheet.scripting import ScriptProcess, ScriptResult

if TYPE_CHECKING:
    from sheet.script_dialog import ScriptWorkspace


def run_script(workspace: ScriptWorkspace) -> None:
    if workspace.runner is not None:
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
    workspace.output.setPlainText("Running script…")
    path = workspace.external_paths.get(workspace.active_name)
    workspace.runner = ScriptProcess(source, workspace.model.workbook, str(path) if path else None)
    workspace.runner.start()
    workspace.timer.start()
    set_running(workspace, True)


def stop_script(workspace: ScriptWorkspace) -> None:
    if workspace.runner is None:
        return
    workspace.runner.stop()
    workspace.runner = None
    workspace.timer.stop()
    workspace.output.appendPlainText("\nScript stopped.")
    set_running(workspace, False)


def poll_runner(workspace: ScriptWorkspace) -> None:
    if workspace.runner is None:
        return
    result = workspace.runner.poll()
    if result is None:
        return
    workspace.runner = None
    workspace.timer.stop()
    set_running(workspace, False)
    finish_script(workspace, result)


def finish_script(workspace: ScriptWorkspace, result: ScriptResult) -> None:
    output = result.output.rstrip()
    workspace.output.setPlainText(
        output or ("Script failed." if result.failed else "Script finished.")
    )
    if result.failed:
        matches = re.findall(r'File "(?:<sheet-script>|[^"]+)", line (\d+)', result.output)
        if matches:
            workspace._go_to_line(int(matches[-1]))
        return
    workspace.model.apply_script_changes(result.changes, result.rows, result.columns)
    workspace.output.appendPlainText(
        f"\nApplied {len(result.changes)} cell change(s) as one undoable action."
    )


def set_running(workspace: ScriptWorkspace, running: bool) -> None:
    workspace.run_button.setEnabled(not running)
    workspace.stop_button.setEnabled(running)
    workspace.library.set_running(running, workspace.active_name in workspace.external_paths)
    workspace.editor.setReadOnly(running)
