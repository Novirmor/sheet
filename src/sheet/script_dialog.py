from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from urllib.parse import quote

from PySide6.QtCore import QSettings, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QUndoCommand
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from sheet.code_editor import CodeEditor, LineNumberArea, PythonHighlighter
from sheet.coordinates import parse_cell_reference
from sheet.external_session import ExternalScriptProcess, ExternalScriptSession
from sheet.model import SpreadsheetModel
from sheet.python_environment import selected_interpreter
from sheet.python_environment_dialog import PythonEnvironmentDialog
from sheet.script_api import api_help_html
from sheet.script_documents import (
    available_name,
    delete_script,
    export_script,
    import_script,
    new_script,
    reload_external_script,
    rename_script,
    save_external_script,
)
from sheet.script_execution import (
    finish_script,
    fresh_run_script,
    interrupt_session,
    poll_runner,
    restart_session,
    run_console,
    run_script,
    run_selection,
    set_running,
    stop_script,
)
from sheet.script_inspector import PreviewTableModel, VariableExplorer
from sheet.script_intelligence import (
    Diagnostic,
    apply_rename_plan,
    folding_ranges,
    outline,
    rename_plan,
    request_syntax_diagnostics,
    search_sources,
)
from sheet.script_library import ScriptLibraryPanel
from sheet.script_source import ScriptSourcePanel
from sheet.scripting import (
    DisplayResult,
    ExceptionInfo,
    ScriptProcess,
    ScriptResult,
    ScriptSession,
    SessionInspection,
)

__all__ = ["CodeEditor", "LineNumberArea", "PythonHighlighter", "ScriptWorkspace"]

STARTER_SCRIPT = """# Use the sheet API from Python.
sheet.write("A1", [["Item", "Amount"], ["Coffee", 4.50]])
sheet.set("B4", "=sum(B2:B3)")
print(sheet.range("A1:B4"))
"""

MAX_RUN_HISTORY = 20


@dataclass(slots=True)
class RunHistoryEntry:
    source: str
    source_id: str
    source_version: int
    duration_ms: int
    failed: bool


class ScriptSourcesCommand(QUndoCommand):
    def __init__(
        self, workspace: ScriptWorkspace, previous: dict[str, str], updated: dict[str, str]
    ) -> None:
        super().__init__("Rename Python symbol")
        self.workspace = workspace
        self.previous = previous
        self.updated = updated

    def redo(self) -> None:
        self.workspace._apply_script_sources(self.updated)

    def undo(self) -> None:
        self.workspace._apply_script_sources(self.previous)


class ScriptWorkspace(QDockWidget):
    def __init__(self, model: SpreadsheetModel, parent: QWidget | None = None) -> None:
        super().__init__("Python", parent)
        self.setObjectName("pythonWorkspace")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.model = model
        self.active_name = ""
        self.external_paths: dict[str, Path] = {}
        self._source_dirty = False
        self.runner: ScriptProcess | ExternalScriptProcess | None = None
        self.session: ScriptSession | ExternalScriptSession | None = None
        self.session_run_id = ""
        self.source_version = 0
        self.source_versions: dict[str, int] = {}
        self.external_dirty: set[str] = set()
        self.cursor_positions: dict[str, tuple[int, int]] = {}
        self.navigation_history: list[tuple[str, int, int]] = []
        self.navigation_index = -1
        self.console_version = 0
        self.console_history: list[str] = []
        self.console_history_index = 0
        self.run_history: list[RunHistoryEntry] = []
        self.environment_dialog: PythonEnvironmentDialog | None = None
        self._pending_source = ""
        self._pending_source_id = ""
        self._pending_source_version = 0
        self._pending_started = 0.0
        self.editor = CodeEditor(STARTER_SCRIPT)
        self.highlighter = PythonHighlighter(self.editor)
        self.output = QPlainTextEdit()
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._poll_runner)
        self.source_timer = QTimer(self)
        self.source_timer.setSingleShot(True)
        self.source_timer.setInterval(400)
        self.source_timer.timeout.connect(self.sync_active_script)
        self.diagnostics_timer = QTimer(self)
        self.diagnostics_timer.setSingleShot(True)
        self.diagnostics_timer.setInterval(300)
        self.diagnostics_timer.timeout.connect(self._request_diagnostics)
        self._build_ui()
        self.editor.textChanged.connect(self._queue_source_sync)
        self.editor.cursorPositionChanged.connect(self._update_position)
        self._load_scripts()

    def set_model(self, model: SpreadsheetModel) -> None:
        self.stop_script()
        self.model = model
        self.external_paths = {}
        self.clear_console_history()
        self.clear_run_history()
        self.clear_results()
        self.variable_explorer.set_variables(())
        self._load_scripts()

    def sync_active_script(self) -> None:
        self.source_timer.stop()
        if self.active_name and self._source_dirty:
            self.model.workbook.set_script(self.active_name, self.editor.toPlainText())
            self._source_dirty = False
            self._update_script_state()

    def _queue_source_sync(self) -> None:
        self.source_version += 1
        if self.active_name:
            self.source_versions[self.active_name] = self.source_version
            self._source_dirty = True
            if self.active_name in self.external_paths:
                self.external_dirty.add(self.active_name)
            self._update_script_state()
            self.source_timer.start()
            self._update_analysis()

    def _build_ui(self) -> None:
        self.setMinimumWidth(620)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText("Write a Python script")
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setPlaceholderText("Script output appears here")
        self.stdout_output = QPlainTextEdit()
        self.stderr_output = QPlainTextEdit()
        for stream in (self.stdout_output, self.stderr_output):
            stream.setReadOnly(True)
            stream.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.exception_view = QTextBrowser()
        self.exception_view.setOpenLinks(False)
        self.exception_view.anchorClicked.connect(self._open_exception_frame)
        self.display_model = PreviewTableModel(self)
        self.display_table = QTableView()
        self.display_table.setModel(self.display_model)
        self.display_text = QTextBrowser()
        display_panel = QWidget()
        display_layout = QVBoxLayout(display_panel)
        display_layout.setContentsMargins(0, 0, 0, 0)
        display_layout.addWidget(self.display_text)
        display_layout.addWidget(self.display_table)
        self.variable_explorer = VariableExplorer(
            self._request_variable_page,
            self._copy_inspected_selection,
            self._write_inspected_page,
            self,
        )
        self.console_input = QPlainTextEdit()
        self.console_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.console_input.setPlaceholderText("Console command. Ctrl+Enter runs multiline input.")

        self.library = ScriptLibraryPanel(
            self._select_script,
            self._new_script,
            self._rename_script,
            self._delete_script,
            self._import_script,
            self._export_script,
            self._save_external_script,
            self._reload_external_script,
        )
        self.script_list = self.library.script_list

        self.source_panel = ScriptSourcePanel(
            self.editor,
            self._find_next,
            self._search_library,
            self._open_outline_line,
            self._toggle_current_fold,
            self.editor.unfold_all,
            self._go_to_definition,
            self._find_references,
            self._rename_symbol,
            self._navigate_back,
            self._navigate_forward,
        )
        self.source_title = self.source_panel.title
        self.position_label = self.source_panel.position
        self.search = self.source_panel.search
        self.editor.assistanceChanged.connect(self.source_panel.assistance.setText)
        self.source_panel.library_results.itemActivated.connect(self._open_library_result)

        help_panel = QTextBrowser()
        help_panel.setOpenExternalLinks(True)
        help_panel.setHtml(api_help_html())

        editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_splitter.addWidget(self.library)
        editor_splitter.addWidget(self.source_panel)
        editor_splitter.addWidget(help_panel)
        editor_splitter.setSizes([155, 455, 230])

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        results_tabs = QTabWidget()
        results_tabs.addTab(self.output, "Output")
        results_tabs.addTab(self.stdout_output, "Stdout")
        results_tabs.addTab(self.stderr_output, "Stderr")
        results_tabs.addTab(self.exception_view, "Exception")
        results_tabs.addTab(display_panel, "Results")
        results_tabs.addTab(self.variable_explorer, "Variables")
        output_layout.addWidget(results_tabs)
        console_title = QHBoxLayout()
        console_title.addWidget(QLabel("Console"))
        console_title.addStretch()
        previous_button = QPushButton("Previous")
        previous_button.clicked.connect(lambda: self._move_console_history(-1))
        console_title.addWidget(previous_button)
        next_button = QPushButton("Next")
        next_button.clicked.connect(lambda: self._move_console_history(1))
        console_title.addWidget(next_button)
        clear_history_button = QPushButton("Clear history")
        clear_history_button.clicked.connect(self.clear_console_history)
        console_title.addWidget(clear_history_button)
        output_layout.addLayout(console_title)
        output_layout.addWidget(self.console_input)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_splitter)
        splitter.addWidget(output_panel)
        splitter.setSizes([460, 190])

        clear_button = QPushButton("Clear output")
        clear_button.clicked.connect(self.clear_results)
        self.run_history_box = QComboBox()
        self.run_history_box.setMinimumWidth(180)
        self.run_history_box.addItem("No captured runs")
        self.rerun_button = QPushButton("Rerun captured")
        self.rerun_button.setEnabled(False)
        self.rerun_button.clicked.connect(self.rerun_captured)
        self.run_button = QPushButton("Run Script  Ctrl+Enter")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run_script)
        self.fresh_run_button = QPushButton("Fresh Run")
        self.fresh_run_button.clicked.connect(self.fresh_run_script)
        self.selection_run_button = QPushButton("Run Selection")
        self.selection_run_button.clicked.connect(self.run_selection)
        self.console_run_button = QPushButton("Run Console")
        self.console_run_button.clicked.connect(self.run_console)
        self.restart_button = QPushButton("Restart Session")
        self.restart_button.clicked.connect(self.restart_session)
        self.interrupt_button = QPushButton("Interrupt")
        self.interrupt_button.setEnabled(False)
        self.interrupt_button.clicked.connect(self.interrupt_session)
        environment_button = QPushButton("Environment")
        environment_button.clicked.connect(self.show_environment)
        self.stop_button = self.interrupt_button
        QShortcut(QKeySequence("Ctrl+Return"), self.editor, self.run_script)
        QShortcut(QKeySequence("Ctrl+Return"), self.console_input, self.run_console)
        QShortcut(QKeySequence.StandardKey.Find, self, self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+G"), self.editor, self._go_to_line_prompt)
        QShortcut(QKeySequence("F12"), self.editor, self._go_to_definition)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self.editor, self._rename_symbol)

        buttons = QHBoxLayout()
        buttons.addWidget(clear_button)
        buttons.addWidget(self.run_history_box)
        buttons.addWidget(self.rerun_button)
        buttons.addStretch()
        buttons.addWidget(environment_button)
        buttons.addWidget(self.restart_button)
        buttons.addWidget(self.interrupt_button)
        buttons.addWidget(self.console_run_button)
        buttons.addWidget(self.selection_run_button)
        buttons.addWidget(self.fresh_run_button)
        buttons.addWidget(self.run_button)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(splitter)
        layout.addLayout(buttons)
        self.setWidget(content)

    def _load_scripts(self, selected: str | None = None) -> None:
        scripts = self.model.workbook.scripts
        names = list(scripts) or ["main"]
        name = selected if selected in names else names[0]
        blocker = QSignalBlocker(self.script_list)
        self.script_list.clear()
        self.script_list.addItems(names)
        self.script_list.setCurrentRow(names.index(name))
        del blocker
        self.active_name = name
        self._set_editor_source(scripts.get(name, STARTER_SCRIPT))
        self._update_script_state()

    def _set_editor_source(self, source: str) -> None:
        blocker = QSignalBlocker(self.editor)
        self.editor.setPlainText(source)
        del blocker
        self._source_dirty = False
        self.source_version = self.source_versions.get(self.active_name, 0)
        self._update_position()
        self._update_analysis()

    def _select_script(self, name: str) -> None:
        if not name or name == self.active_name:
            return
        if (
            self.active_name in self.external_dirty
            and QMessageBox.question(
                self,
                "Linked script has unsaved changes",
                "This script changed in the workspace but was not saved to its linked file. "
                "Switch anyway?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            blocker = QSignalBlocker(self.script_list)
            self.script_list.setCurrentRow(
                (list(self.model.workbook.scripts) or ["main"]).index(self.active_name)
            )
            del blocker
            return
        cursor = self.editor.textCursor()
        self.cursor_positions[self.active_name] = (
            cursor.blockNumber() + 1,
            cursor.columnNumber() + 1,
        )
        self.sync_active_script()
        self.active_name = name
        names = list(self.model.workbook.scripts) or ["main"]
        if self.script_list.currentRow() != names.index(name):
            blocker = QSignalBlocker(self.script_list)
            self.script_list.setCurrentRow(names.index(name))
            del blocker
        self._set_editor_source(self.model.workbook.scripts.get(name, STARTER_SCRIPT))
        if position := self.cursor_positions.get(name):
            self._go_to_line(*position)
        self._update_script_state()

    @property
    def document_id(self) -> str:
        return self.script_document_id(self.active_name)

    def script_document_id(self, name: str) -> str:
        return f"sheet://{self.model.workbook.document_id}/scripts/{quote(name, safe='')}"

    def _new_script(self) -> None:
        new_script(self)

    def _rename_script(self) -> None:
        rename_script(self)

    def _delete_script(self) -> None:
        delete_script(self)

    def _import_script(self) -> None:
        import_script(self)

    def _export_script(self) -> None:
        export_script(self)

    def _save_external_script(self) -> None:
        save_external_script(self)

    def _reload_external_script(self) -> None:
        reload_external_script(self)

    def _available_name(self, base: str) -> str:
        return available_name(base, self.model.workbook.scripts)

    def _find_next(self) -> None:
        text = self.search.text()
        if text and not self.editor.find(text):
            cursor = self.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(text)

    def _go_to_line_prompt(self) -> None:
        line, accepted = QInputDialog.getInt(
            self, "Go to line", "Line number:", self.editor.textCursor().blockNumber() + 1, 1
        )
        if accepted:
            self._go_to_line(line)

    def _go_to_line(self, line: int, column: int = 1) -> None:
        block = self.editor.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = self.editor.textCursor()
        cursor.setPosition(block.position() + max(0, column - 1))
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()

    def _update_analysis(self) -> None:
        source = self.editor.toPlainText()
        self.editor.set_folding_ranges(folding_ranges(source))
        self.source_panel.outline.clear()
        for item in outline(source):
            entry = QListWidgetItem(f"{'  ' * item.depth}{item.kind} {item.name}  :{item.line}")
            entry.setData(32, item.line)
            self.source_panel.outline.addItem(entry)
        self.diagnostics_timer.start()

    def _request_diagnostics(self) -> None:
        request_syntax_diagnostics(
            self.document_id,
            self.editor.toPlainText(),
            self.source_version,
            self._receive_diagnostics,
        )

    def _receive_diagnostics(
        self, name: str, version: int, diagnostics: tuple[Diagnostic, ...]
    ) -> None:
        if name != self.document_id or version != self.source_version:
            return
        current = tuple(diagnostics)
        self.editor.set_diagnostics(current)
        self.source_panel.diagnostics.setText(
            ""
            if not current
            else (
                f"Syntax: line {current[0].line}, column {current[0].column}: {current[0].message}"
            )
        )

    def _open_outline_line(self, line: int) -> None:
        self._navigate_to(self.active_name, line, 1)

    def _toggle_current_fold(self) -> None:
        self.editor.toggle_fold_at_line(self.editor.textCursor().blockNumber() + 1)

    def _all_sources(self) -> dict[str, str]:
        sources = dict(self.model.workbook.scripts)
        if self.active_name:
            sources[self.active_name] = self.editor.toPlainText()
        return sources

    def _search_library(self) -> None:
        self.sync_active_script()
        matches = search_sources(
            self._all_sources(),
            self.source_panel.library_search.text(),
            case_sensitive=self.source_panel.case_sensitive.isChecked(),
            whole_word=self.source_panel.whole_word.isChecked(),
        )
        self.source_panel.library_results.clear()
        for match in matches:
            item = QListWidgetItem(f"{match.source_name}:{match.line}: {match.preview}")
            item.setData(32, (match.source_name, match.line, match.column))
            self.source_panel.library_results.addItem(item)
        if not matches and self.source_panel.library_search.text():
            self.source_panel.library_results.addItem("No stored-script matches")

    def _open_library_result(self, item: QListWidgetItem) -> None:
        data = item.data(32)
        if not isinstance(data, tuple):
            return
        name, line, column = data
        if name != self.active_name:
            self._navigate_to(name, line, column)
            return
        self._navigate_to(name, line, column)

    def _record_navigation(self) -> None:
        cursor = self.editor.textCursor()
        location = (self.active_name, cursor.blockNumber() + 1, cursor.columnNumber() + 1)
        if (
            self.navigation_index >= 0
            and self.navigation_history[self.navigation_index] == location
        ):
            return
        del self.navigation_history[self.navigation_index + 1 :]
        self.navigation_history.append(location)
        self.navigation_index = len(self.navigation_history) - 1

    def _navigate_to(self, name: str, line: int, column: int) -> None:
        self._record_navigation()
        if name != self.active_name:
            self._select_script(name)
            if name != self.active_name:
                return
        self._go_to_line(line, column)
        self._record_navigation()

    def _navigate_back(self) -> None:
        if self.navigation_index <= 0:
            return
        self.navigation_index -= 1
        name, line, column = self.navigation_history[self.navigation_index]
        if name != self.active_name:
            self._select_script(name)
        if name == self.active_name:
            self._go_to_line(line, column)

    def _navigate_forward(self) -> None:
        if self.navigation_index + 1 >= len(self.navigation_history):
            return
        self.navigation_index += 1
        name, line, column = self.navigation_history[self.navigation_index]
        if name != self.active_name:
            self._select_script(name)
        if name == self.active_name:
            self._go_to_line(line, column)

    def _go_to_definition(self) -> None:
        cursor = self.editor.textCursor()
        plan = rename_plan(
            self._all_sources(),
            self.source_versions | {self.active_name: self.source_version},
            self.active_name,
            cursor.blockNumber() + 1,
            cursor.columnNumber(),
            "_definition_probe",
        )
        if plan is None:
            self.source_panel.assistance.setText(
                "Definition unavailable: select a statically resolved local or module name."
            )
            return
        edit = next(iter(plan.edits[self.active_name]))
        self._navigate_to(self.active_name, edit.line, 1)

    def _find_references(self) -> None:
        cursor = self.editor.textCursor()
        plan = rename_plan(
            self._all_sources(),
            self.source_versions | {self.active_name: self.source_version},
            self.active_name,
            cursor.blockNumber() + 1,
            cursor.columnNumber(),
            "_reference_probe",
        )
        self.source_panel.library_results.clear()
        if plan is None:
            self.source_panel.library_results.addItem("References unavailable for this symbol")
            return
        for source_name, edits in plan.edits.items():
            for edit in edits:
                item = QListWidgetItem(f"{source_name}:{edit.line}: {plan.symbol}")
                item.setData(32, (source_name, edit.line, 1))
                self.source_panel.library_results.addItem(item)

    def _rename_symbol(self) -> None:
        cursor = self.editor.textCursor()
        new_name, accepted = QInputDialog.getText(self, "Rename Python symbol", "New identifier:")
        if not accepted:
            return
        sources = self._all_sources()
        versions = self.source_versions | {self.active_name: self.source_version}
        plan = rename_plan(
            sources,
            versions,
            self.active_name,
            cursor.blockNumber() + 1,
            cursor.columnNumber(),
            new_name,
        )
        if plan is None:
            QMessageBox.information(
                self,
                "Rename Python symbol",
                "Only statically resolved local or module identifiers can be renamed without a "
                "semantic backend.",
            )
            return
        preview = "\n".join(
            f"{name}: {len(edits)} occurrence(s)" for name, edits in plan.edits.items()
        )
        if (
            QMessageBox.question(
                self,
                "Preview Python symbol rename",
                f"Rename {plan.symbol} to {plan.replacement}?\n\n{preview}\n\n"
                "Linked files remain unsaved.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if any(
            self.source_versions.get(name, 0) != version
            for name, version in plan.source_versions.items()
        ):
            QMessageBox.warning(
                self, "Rename Python symbol", "Sources changed; preview is stale. Recompute it."
            )
            return
        self.model.undo_stack.push(
            ScriptSourcesCommand(
                self, dict(self.model.workbook.scripts), apply_rename_plan(sources, plan)
            )
        )

    def _apply_script_sources(self, sources: dict[str, str]) -> None:
        self.model.workbook.replace_scripts(sources)
        for name in sources:
            self.source_versions[name] = self.source_versions.get(name, 0) + 1
        if self.active_name in sources:
            self._set_editor_source(sources[self.active_name])
            if self.active_name in self.external_paths:
                self.external_dirty.add(self.active_name)
        self._update_script_state()

    def _update_position(self) -> None:
        cursor = self.editor.textCursor()
        self.position_label.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.columnNumber() + 1}"
        )

    def run_script(self) -> None:
        run_script(self)

    def fresh_run_script(self) -> None:
        fresh_run_script(self)

    def run_selection(self) -> None:
        run_selection(self)

    def run_console(self) -> None:
        run_console(self)

    def interrupt_session(self) -> None:
        interrupt_session(self)

    def restart_session(self) -> None:
        restart_session(self)

    def stop_script(self) -> None:
        stop_script(self)

    def show_environment(self) -> None:
        if self.environment_dialog is None:
            self.environment_dialog = PythonEnvironmentDialog(self, self)
        self.environment_dialog.show()
        self.environment_dialog.raise_()
        self.environment_dialog.activateWindow()

    def external_environment_selected(self) -> bool:
        return selected_interpreter(QSettings()) is not None

    def external_interpreter(self) -> Path | None:
        """The validated external interpreter selected in local settings, if any."""
        return selected_interpreter(QSettings())

    def environment_changed(self, *, external: bool) -> None:
        self.stop_script()
        self.clear_results()
        self.clear_run_history()
        self.variable_explorer.set_variables(())
        self.editor.set_diagnostics(())
        self.source_panel.diagnostics.clear()
        self.output.setPlainText(
            "External interpreter selected. The existing session was stopped and variables/results "
            "were cleared. New runs will launch with the selected interpreter."
            if external
            else "Application runtime restored. The existing session was stopped and "
            "variables/results "
            "were cleared. Use Run or Restart Session to start a new session."
        )

    def _poll_runner(self) -> None:
        poll_runner(self)

    def _finish_script(self, result: ScriptResult) -> None:
        finish_script(self, result)

    def _set_running(self, running: bool) -> None:
        set_running(self, running)

    def _move_console_history(self, direction: int) -> None:
        if not self.console_history:
            return
        self.console_history_index = min(
            len(self.console_history), max(0, self.console_history_index + direction)
        )
        self.console_input.setPlainText(
            ""
            if self.console_history_index == len(self.console_history)
            else self.console_history[self.console_history_index]
        )

    def clear_console_history(self) -> None:
        self.console_history.clear()
        self.console_history_index = 0

    def begin_run(self, source: str, source_id: str, source_version: int) -> None:
        self._pending_source = source
        self._pending_source_id = source_id
        self._pending_source_version = source_version
        self._pending_started = monotonic()
        self.stdout_output.clear()
        self.stderr_output.clear()
        self.exception_view.clear()
        self.display_text.clear()
        self.display_model.beginResetModel()
        self.display_model.columns = ()
        self.display_model.index_values = ()
        self.display_model.rows = ()
        self.display_model.endResetModel()
        self.variable_explorer.set_running(True)

    def append_output(self, channel: str, text: str) -> None:
        stream = self.stdout_output if channel == "stdout" else self.stderr_output
        stream.insertPlainText(text)
        self.output.insertPlainText(text)

    def present_result(
        self,
        *,
        stdout: str,
        stderr: str,
        exception: ExceptionInfo | None,
        displays: tuple[DisplayResult, ...],
        duration_ms: int,
    ) -> None:
        if not self.stdout_output.toPlainText() and stdout:
            self.stdout_output.setPlainText(stdout)
        if not self.stderr_output.toPlainText() and stderr:
            self.stderr_output.setPlainText(stderr)
        if exception is not None:
            frame_links = "".join(
                f'<li><a href="frame:{index}">{frame.filename}:{frame.line} '
                f"in {frame.function}</a></li>"
                for index, frame in enumerate(exception.frames)
            )
            self._exception_frames = exception.frames
            self.exception_view.setHtml(
                f"<b>{exception.type_name}</b>: {exception.message}<ul>{frame_links}</ul>"
            )
        if displays:
            display = displays[-1]
            self.display_text.setPlainText(display.text)
            if display.kind == "table":
                from sheet.scripting import VariablePage

                self.display_model.set_page(
                    VariablePage(
                        "",
                        display.columns,
                        (),
                        display.index,
                        display.rows,
                        len(display.rows),
                        len(display.columns),
                        display.partial,
                    )
                )
        self.record_run(duration_ms, exception is not None)

    def record_run(self, duration_ms: int, failed: bool) -> None:
        if not self._pending_source:
            return
        self.run_history.append(
            RunHistoryEntry(
                self._pending_source,
                self._pending_source_id,
                self._pending_source_version,
                duration_ms or int((monotonic() - self._pending_started) * 1000),
                failed,
            )
        )
        del self.run_history[:-MAX_RUN_HISTORY]
        self.run_history_box.clear()
        for index, entry in enumerate(self.run_history, start=1):
            self.run_history_box.addItem(
                f"{index}. {entry.source_id} "
                f"{'failed' if entry.failed else 'finished'} ({entry.duration_ms} ms)",
                index - 1,
            )
        self.run_history_box.setCurrentIndex(self.run_history_box.count() - 1)
        self.rerun_button.setEnabled(bool(self.run_history))
        self._pending_source = ""

    def clear_run_history(self) -> None:
        self.run_history.clear()
        if hasattr(self, "run_history_box"):
            self.run_history_box.clear()
            self.run_history_box.addItem("No captured runs")
            self.rerun_button.setEnabled(False)

    def clear_results(self) -> None:
        self.output.clear()
        self.stdout_output.clear()
        self.stderr_output.clear()
        self.exception_view.clear()
        self.display_text.clear()

    def rerun_captured(self) -> None:
        index = self.run_history_box.currentData()
        if not isinstance(index, int) or not 0 <= index < len(self.run_history):
            return
        from sheet.script_execution import run_captured

        run_captured(self, self.run_history[index])

    def _open_exception_frame(self, url) -> None:
        try:
            index = int(url.toString().partition(":")[2])
            frame = self._exception_frames[index]
        except AttributeError, IndexError, ValueError:
            return
        if frame.source_id != self.active_name:
            self.output.appendPlainText(f"\nTraceback source is not open: {frame.filename}")
            return
        if frame.source_version != self.source_version:
            self.output.appendPlainText(
                "\nTraceback source is stale; it was not applied to this buffer."
            )
            return
        self._go_to_line(frame.line)

    def _request_variable_snapshot(self) -> None:
        if self.session is not None and self.session.state.value == "idle":
            self.session.inspect_variables()

    def _request_variable_page(self, handle: str, start: int) -> None:
        if self.session is not None and self.session.state.value == "idle":
            self.session.inspect_variable_page(handle, start)

    def apply_inspection(self, inspection: SessionInspection) -> None:
        if inspection.error:
            self.variable_explorer.status.setText(inspection.error)
        elif inspection.page is not None:
            self.variable_explorer.set_page(inspection.page)
        else:
            self.variable_explorer.set_variables(inspection.variables)

    def _write_inspected_page(self) -> None:
        page = self.variable_explorer.current_page
        if page is None or not page.rows:
            return
        if page.write_error:
            self.variable_explorer.status.setText(page.write_error)
            return
        destination, accepted = QInputDialog.getText(
            self, "Write DataFrame page", "Destination cell:"
        )
        if not accepted:
            return
        try:
            row, column = parse_cell_reference(destination)
        except ValueError:
            self.variable_explorer.status.setText("Enter a cell reference such as A1.")
            return
        options, accepted = QInputDialog.getItem(
            self,
            "Write options",
            "Include:",
            ["Values", "Values and headers", "Values, headers, and index"],
            1,
            False,
        )
        if not accepted:
            return
        rows = [list(values) for values in page.sheet_rows]
        if options == "Values, headers, and index":
            rows = [[index, *values] for index, values in zip(page.index, rows, strict=True)]
        if options != "Values":
            rows.insert(0, (["index"] if options.endswith("index") else []) + list(page.columns))
        updates = {
            (row + row_offset, column + column_offset): value
            for row_offset, values in enumerate(rows)
            for column_offset, value in enumerate(values)
        }
        conflicts = sum(
            bool(self.model.workbook.raw_value(*coordinate))
            for coordinate in updates
            if coordinate[0] < self.model.workbook.rows
            and coordinate[1] < self.model.workbook.columns
        )
        preview = " | ".join(rows[0][:5])
        message = (
            f"Write {len(rows)} x {len(rows[0])} cells to {destination.upper()}?\n"
            f"Preview: {preview}"
        )
        if conflicts:
            message += f"\nThis overwrites {conflicts} non-empty cell(s)."
        if QMessageBox.question(self, "Confirm write", message) != QMessageBox.StandardButton.Yes:
            return
        self.model.apply_script_changes(
            updates,
            max(self.model.workbook.rows, row + len(rows)),
            max(self.model.workbook.columns, column + len(rows[0])),
        )
        self.variable_explorer.status.setText("Wrote the displayed page as one undoable action.")

    def _copy_inspected_selection(self) -> None:
        indexes = self.variable_explorer.table.selectionModel().selectedIndexes()
        if not indexes:
            return
        top = min(index.row() for index in indexes)
        bottom = max(index.row() for index in indexes)
        left = min(index.column() for index in indexes)
        right = max(index.column() for index in indexes)
        selected = {(index.row(), index.column()) for index in indexes}
        rows = [
            "\t".join(
                str(
                    self.variable_explorer.table_model.data(
                        self.variable_explorer.table_model.index(row, column)
                    )
                )
                if (row, column) in selected
                else ""
                for column in range(left, right + 1)
            )
            for row in range(top, bottom + 1)
        ]
        QApplication.clipboard().setText("\n".join(rows))
        self.variable_explorer.status.setText("Copied selection.")

    def _update_script_state(self) -> None:
        marker = (
            " • modified" if self._source_dirty or self.active_name in self.external_dirty else ""
        )
        self.source_title.setText(f"{self.active_name or 'Script'}{marker}")
        self.library.set_external_actions(self.active_name in self.external_paths)
