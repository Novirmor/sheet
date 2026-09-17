from __future__ import annotations

import ast
import re
from pathlib import Path

from PySide6.QtCore import QRect, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sheet.model import SpreadsheetModel
from sheet.scripting import ScriptProcess, ScriptResult

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
<p><code>sheet.rows</code> / <code>sheet.columns</code></p>
<hr>
<p><b>Security:</b> scripts run in a separate local Python process. They can access your machine
with your user permissions.</p>
"""


class PythonHighlighter(QSyntaxHighlighter):
    _keywords = re.compile(
        r"\b(and|as|assert|break|class|continue|def|del|elif|else|except|False|finally|for|from|"
        r"if|import|in|is|lambda|None|not|or|pass|raise|return|True|try|while|with|yield)\b"
    )
    _builtins = re.compile(
        r"\b(abs|dict|enumerate|float|int|len|list|max|min|print|range|round|str|sum)\b"
    )
    _strings = re.compile(r"(?:'[^'\\]*(?:\\.[^'\\]*)*'|\"[^\"\\]*(?:\\.[^\"\\]*)*\")")
    _comments = re.compile(r"#.*$")

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor.document())
        self._keyword_format = self._format("#7c3aed", bold=True)
        self._builtin_format = self._format("#1557b0")
        self._string_format = self._format("#0f766e")
        self._comment_format = self._format("#667085", italic=True)

    def highlightBlock(self, text: str) -> None:
        for pattern, text_format in (
            (self._keywords, self._keyword_format),
            (self._builtins, self._builtin_format),
            (self._strings, self._string_format),
            (self._comments, self._comment_format),
        ):
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), text_format)

    @staticmethod
    def _format(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))
        text_format.setFontWeight(700 if bold else 400)
        text_format.setFontItalic(italic)
        return text_format


class LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, source: str) -> None:
        super().__init__(source)
        self.line_number_area = LineNumberArea(self)
        self.completer = QCompleter(
            ["clear", "columns", "get", "range", "raw", "rows", "set", "write"], self
        )
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.activated.connect(self._insert_completion)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()

    def line_number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#f4f6f9"))
        painter.setPen(QColor("#98a2b3"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        content = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(content.left(), content.top(), self.line_number_width(), content.height())
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        popup = self.completer.popup()
        if (
            popup is not None
            and popup.isVisible()
            and event.key()
            in (
                Qt.Key.Key_Enter,
                Qt.Key.Key_Return,
                Qt.Key.Key_Escape,
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
            )
        ):
            event.ignore()
            return
        super().keyPressEvent(event)
        prefix = self._completion_prefix()
        if len(prefix) < 2:
            if popup is not None:
                popup.hide()
            return
        self.completer.setCompletionPrefix(prefix)
        if popup is None:
            return
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rectangle = self.cursorRect()
        rectangle.setWidth(
            popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width()
        )
        self.completer.complete(rectangle)

    def _completion_prefix(self) -> str:
        cursor = self.textCursor()
        cursor.select(cursor.SelectionType.WordUnderCursor)
        return cursor.selectedText()

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        prefix = self._completion_prefix()
        cursor.insertText(completion[len(prefix) :])
        self.setTextCursor(cursor)

    def _highlight_current_line(self) -> None:
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#f2f7ff"))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def _update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_line_number_area(self, rectangle: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rectangle.y(), self.line_number_area.width(), rectangle.height()
            )
        if rectangle.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)


class ScriptWorkspace(QDockWidget):
    def __init__(self, model: SpreadsheetModel, parent: QWidget | None = None) -> None:
        super().__init__("Python", parent)
        self.setObjectName("pythonWorkspace")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
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

        self.script_list = QListWidget()
        self.script_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.script_list.currentTextChanged.connect(self._select_script)
        new_button = QPushButton("New")
        new_button.clicked.connect(self._new_script)
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self._rename_script)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_script)
        self.import_button = QPushButton("Import…")
        self.import_button.clicked.connect(self._import_script)
        self.export_button = QPushButton("Export…")
        self.export_button.clicked.connect(self._export_script)
        self.save_external_button = QPushButton("Save external")
        self.save_external_button.clicked.connect(self._save_external_script)
        self.reload_button = QPushButton("Reload")
        self.reload_button.clicked.connect(self._reload_external_script)
        explorer = QWidget()
        explorer_layout = QVBoxLayout(explorer)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        explorer_layout.addWidget(QLabel("Workbook scripts"))
        explorer_layout.addWidget(self.script_list)
        explorer_layout.addWidget(new_button)
        explorer_layout.addWidget(self.rename_button)
        explorer_layout.addWidget(self.delete_button)
        explorer_layout.addWidget(self.import_button)
        explorer_layout.addWidget(self.export_button)
        explorer_layout.addWidget(self.save_external_button)
        explorer_layout.addWidget(self.reload_button)

        self.source_title = QLabel()
        self.position_label = QLabel()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find in script")
        self.search.returnPressed.connect(self._find_next)
        find_button = QPushButton("Find next")
        find_button.clicked.connect(self._find_next)
        find_layout = QHBoxLayout()
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.addWidget(self.search)
        find_layout.addWidget(find_button)
        source_panel = QWidget()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_header = QHBoxLayout()
        source_header.addWidget(self.source_title)
        source_header.addStretch()
        source_header.addWidget(self.position_label)
        source_layout.addLayout(source_header)
        source_layout.addLayout(find_layout)
        source_layout.addWidget(self.editor)

        help_panel = QTextBrowser()
        help_panel.setOpenExternalLinks(True)
        help_panel.setHtml(API_HELP)

        editor_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_splitter.addWidget(explorer)
        editor_splitter.addWidget(source_panel)
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
        name, accepted = QInputDialog.getText(self, "New script", "Script name:")
        name = name.strip()
        if not accepted or not name:
            return
        if name in self.model.workbook.scripts:
            QMessageBox.warning(self, "Script already exists", f'"{name}" already exists.')
            return
        self.sync_active_script()
        self.model.workbook.set_script(name, "")
        self._load_scripts(name)

    def _rename_script(self) -> None:
        if not self.active_name:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename script", "Script name:", text=self.active_name
        )
        name = name.strip()
        if not accepted or not name or name == self.active_name:
            return
        if name in self.model.workbook.scripts:
            QMessageBox.warning(self, "Script already exists", f'"{name}" already exists.')
            return
        self.sync_active_script()
        source = self.model.workbook.scripts.get(self.active_name, self.editor.toPlainText())
        self.model.workbook.set_script(name, source)
        self.model.workbook.delete_script(self.active_name)
        if path := self.external_paths.pop(self.active_name, None):
            self.external_paths[name] = path
        self._load_scripts(name)

    def _delete_script(self) -> None:
        if not self.active_name:
            return
        self.sync_active_script()
        self.model.workbook.delete_script(self.active_name)
        self.external_paths.pop(self.active_name, None)
        self._load_scripts()

    def _import_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Python script", "", "Python (*.py)")
        if not path:
            return
        selected = Path(path)
        try:
            source = selected.read_text()
        except OSError as error:
            QMessageBox.critical(self, "Could not import script", str(error))
            return
        self.sync_active_script()
        name = self._available_name(selected.stem or "script")
        self.model.workbook.set_script(name, source)
        self.external_paths[name] = selected
        self._load_scripts(name)

    def _export_script(self) -> None:
        self.sync_active_script()
        initial = str(self.external_paths.get(self.active_name, Path(f"{self.active_name}.py")))
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Python script", initial, "Python (*.py)"
        )
        if not path:
            return
        selected = Path(path).with_suffix(".py") if not Path(path).suffix else Path(path)
        try:
            selected.write_text(self.editor.toPlainText())
        except OSError as error:
            QMessageBox.critical(self, "Could not export script", str(error))
            return
        self.external_paths[self.active_name] = selected
        self._update_script_state()

    def _save_external_script(self) -> None:
        path = self.external_paths.get(self.active_name)
        if path is None:
            self._export_script()
            return
        self.sync_active_script()
        try:
            path.write_text(self.editor.toPlainText())
        except OSError as error:
            QMessageBox.critical(self, "Could not save external script", str(error))
            return
        self.output.setPlainText(f"Saved external script to {path}")

    def _reload_external_script(self) -> None:
        path = self.external_paths.get(self.active_name)
        if path is None:
            return
        try:
            source = path.read_text()
        except OSError as error:
            QMessageBox.critical(self, "Could not reload script", str(error))
            return
        self._set_editor_source(source)
        self._source_dirty = True
        self.sync_active_script()

    def _available_name(self, base: str) -> str:
        name = base
        suffix = 2
        while name in self.model.workbook.scripts:
            name = f"{base} {suffix}"
            suffix += 1
        return name

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
        if self.runner is not None:
            return
        self.sync_active_script()
        source = self.editor.toPlainText()
        try:
            ast.parse(source)
        except SyntaxError as error:
            line = error.lineno or 1
            column = error.offset or 1
            self.output.setPlainText(f"Syntax error at line {line}, column {column}: {error.msg}")
            self._go_to_line(line, column)
            return
        self.output.setPlainText("Running script…")
        path = self.external_paths.get(self.active_name)
        self.runner = ScriptProcess(source, self.model.workbook, str(path) if path else None)
        self.runner.start()
        self.timer.start()
        self._set_running(True)

    def stop_script(self) -> None:
        if self.runner is None:
            return
        self.runner.stop()
        self.runner = None
        self.timer.stop()
        self.output.appendPlainText("\nScript stopped.")
        self._set_running(False)

    def _poll_runner(self) -> None:
        if self.runner is None:
            return
        result = self.runner.poll()
        if result is None:
            return
        self.runner = None
        self.timer.stop()
        self._set_running(False)
        self._finish_script(result)

    def _finish_script(self, result: ScriptResult) -> None:
        output = result.output.rstrip()
        self.output.setPlainText(
            output or ("Script failed." if result.failed else "Script finished.")
        )
        if result.failed:
            matches = re.findall(r'File "(?:<sheet-script>|[^"]+)", line (\d+)', result.output)
            if matches:
                self._go_to_line(int(matches[-1]))
            return
        self.model.apply_script_changes(result.changes, result.rows, result.columns)
        self.output.appendPlainText(
            f"\nApplied {len(result.changes)} cell change(s) as one undoable action."
        )

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.rename_button.setEnabled(not running)
        self.delete_button.setEnabled(not running)
        self.import_button.setEnabled(not running)
        self.export_button.setEnabled(not running)
        self.save_external_button.setEnabled(
            not running and self.active_name in self.external_paths
        )
        self.reload_button.setEnabled(not running and self.active_name in self.external_paths)
        self.script_list.setEnabled(not running)
        self.editor.setReadOnly(running)

    def _update_script_state(self) -> None:
        marker = " • modified" if self._source_dirty else ""
        self.source_title.setText(f"{self.active_name or 'Script'}{marker}")
        self.reload_button.setEnabled(self.active_name in self.external_paths)
        self.save_external_button.setEnabled(self.active_name in self.external_paths)
