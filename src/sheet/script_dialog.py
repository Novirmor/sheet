from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from sheet.code_editor import CodeEditor, LineNumberArea, PythonHighlighter
from sheet.model import SpreadsheetModel
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
    poll_runner,
    run_script,
    set_running,
    stop_script,
)
from sheet.script_library import ScriptLibraryPanel
from sheet.script_source import ScriptSourcePanel
from sheet.scripting import ScriptProcess, ScriptResult

__all__ = ["CodeEditor", "LineNumberArea", "PythonHighlighter", "ScriptWorkspace"]

STARTER_SCRIPT = """# Use the sheet API from Python.
sheet.write("A1", [["Item", "Amount"], ["Coffee", 4.50]])
sheet.set("B4", "=sum(B2:B3)")
print(sheet.range("A1:B4"))
"""

API_HELP = """
<h3>Sheet API</h3>
<p><code>sheet.get("A1")</code><br>Calculated cell value.</p>
<p><code>sheet.raw("A1")</code><br>Original cell input.</p>
<p><code>sheet.set("A1", value)</code><br>Set one cell.</p>
<p><code>sheet.write("A1", rows)</code><br>Write a rectangular list.</p>
<p><code>sheet.range("A1:C3")</code><br>Read a rectangular range.</p>
<p><code>sheet.clear("A1:C3")</code><br>Clear a range.</p>
<p><code>sheet.dataframe("A1:C3")</code><br>Read a range into Pandas.</p>
<p><code>sheet.write_dataframe("A1", frame)</code><br>Write a Pandas DataFrame.</p>
<p><code>sheet.rows</code> / <code>sheet.columns</code></p>
<p><code>pd</code> and <code>px</code> provide Pandas and Plotly Express.
Use <code>fig.show()</code>
to open a Plotly chart in your browser.</p>
<hr>
<p><b>Security:</b> scripts run in a separate local Python process. They can access your machine
with your user permissions.</p>
"""


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
        self.runner: ScriptProcess | None = None
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
        self._build_ui()
        self.editor.textChanged.connect(self._queue_source_sync)
        self.editor.cursorPositionChanged.connect(self._update_position)
        self._load_scripts()

    def set_model(self, model: SpreadsheetModel) -> None:
        self.stop_script()
        self.model = model
        self.external_paths = {}
        self._load_scripts()

    def sync_active_script(self) -> None:
        self.source_timer.stop()
        if self.active_name and self._source_dirty:
            self.model.workbook.set_script(self.active_name, self.editor.toPlainText())
            self._source_dirty = False
            self._update_script_state()

    def _queue_source_sync(self) -> None:
        if self.active_name:
            self._source_dirty = True
            self._update_script_state()
            self.source_timer.start()

    def _build_ui(self) -> None:
        self.setMinimumWidth(620)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText("Write a Python script")
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setPlaceholderText("Script output appears here")

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

        self.source_panel = ScriptSourcePanel(self.editor, self._find_next)
        self.source_title = self.source_panel.title
        self.position_label = self.source_panel.position
        self.search = self.source_panel.search

        help_panel = QTextBrowser()
        help_panel.setOpenExternalLinks(True)
        help_panel.setHtml(API_HELP)

        editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_splitter.addWidget(self.library)
        editor_splitter.addWidget(self.source_panel)
        editor_splitter.addWidget(help_panel)
        editor_splitter.setSizes([155, 455, 230])

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(QLabel("Output"))
        output_layout.addWidget(self.output)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_splitter)
        splitter.addWidget(output_panel)
        splitter.setSizes([460, 190])

        clear_button = QPushButton("Clear output")
        clear_button.clicked.connect(self.output.clear)
        self.run_button = QPushButton("Run  Ctrl+Enter")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run_script)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_script)
        QShortcut(QKeySequence("Ctrl+Return"), self.editor, self.run_script)
        QShortcut(QKeySequence.StandardKey.Find, self, self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+G"), self.editor, self._go_to_line_prompt)

        buttons = QHBoxLayout()
        buttons.addWidget(clear_button)
        buttons.addStretch()
        buttons.addWidget(self.stop_button)
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
        self._update_position()

    def _select_script(self, name: str) -> None:
        if not name or name == self.active_name:
            return
        self.sync_active_script()
        self.active_name = name
        self._set_editor_source(self.model.workbook.scripts.get(name, STARTER_SCRIPT))
        self._update_script_state()

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

    def _update_position(self) -> None:
        cursor = self.editor.textCursor()
        self.position_label.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.columnNumber() + 1}"
        )

    def run_script(self) -> None:
        run_script(self)

    def stop_script(self) -> None:
        stop_script(self)

    def _poll_runner(self) -> None:
        poll_runner(self)

    def _finish_script(self, result: ScriptResult) -> None:
        finish_script(self, result)

    def _set_running(self, running: bool) -> None:
        set_running(self, running)

    def _update_script_state(self) -> None:
        marker = " • modified" if self._source_dirty else ""
        self.source_title.setText(f"{self.active_name or 'Script'}{marker}")
        self.library.set_external_actions(self.active_name in self.external_paths)
