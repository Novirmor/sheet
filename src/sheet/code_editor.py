from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, QStringListModel, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QWidget

from sheet.script_api import api_member, api_member_names
from sheet.script_intelligence import Diagnostic


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
    assistanceChanged = Signal(str)

    def __init__(self, source: str) -> None:
        super().__init__(source)
        self.line_number_area = LineNumberArea(self)
        self._completion_model = QStringListModel(self)
        self.completer = QCompleter(self._completion_model, self)
        self._diagnostics: tuple[Diagnostic, ...] = ()
        self._folding_ranges: tuple[tuple[int, int], ...] = ()
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.activated.connect(self._insert_completion)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.cursorPositionChanged.connect(self._update_assistance)
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
        context, prefix = self._completion_context()
        candidates = api_member_names() if context == "sheet" else _completion_words()
        if context != "sheet" and len(prefix) < 2:
            if popup is not None:
                popup.hide()
            return
        self._completion_model.setStringList(candidates)
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

    def _completion_context(self) -> tuple[str, str]:
        cursor = self.textCursor()
        prefix = self._completion_prefix()
        before = self.toPlainText()[: cursor.position() - len(prefix)]
        return ("sheet" if before.endswith("sheet.") else "python"), prefix

    def _insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        prefix = self._completion_prefix()
        cursor.insertText(completion[len(prefix) :])
        self.setTextCursor(cursor)

    def _highlight_current_line(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#f2f7ff"))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        selections.append(selection)
        for diagnostic in self._diagnostics:
            block = self.document().findBlockByNumber(diagnostic.line - 1)
            if not block.isValid():
                continue
            error = QTextEdit.ExtraSelection()
            error.cursor = self.textCursor()
            error.cursor.setPosition(block.position() + max(0, diagnostic.column - 1))
            error.cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            error.format.setUnderlineColor(QColor("#d92d20"))
            error.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            error.format.setToolTip(diagnostic.message)
            selections.append(error)
        self.setExtraSelections(selections)

    def set_diagnostics(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self._diagnostics = diagnostics
        self._highlight_current_line()

    def set_folding_ranges(self, ranges: tuple[tuple[int, int], ...]) -> None:
        self._folding_ranges = ranges

    def toggle_fold_at_line(self, line: int) -> bool:
        for start, end in self._folding_ranges:
            if start != line:
                continue
            first = self.document().findBlockByNumber(start)
            hidden = first.isValid() and first.next().isVisible()
            block = first.next()
            while block.isValid() and block.blockNumber() < end:
                block.setVisible(not hidden)
                block.setLineCount(0 if hidden else 1)
                block = block.next()
            self.document().markContentsDirty(
                first.position(), max(1, block.position() - first.position())
            )
            self.viewport().update()
            return True
        return False

    def unfold_all(self) -> None:
        block = self.document().begin()
        while block.isValid():
            block.setVisible(True)
            block.setLineCount(1)
            block = block.next()
        self.viewport().update()

    def _update_assistance(self) -> None:
        context, prefix = self._completion_context()
        member = api_member(prefix) if context == "sheet" else None
        fallback = (
            "AST local/module navigation is available. Optional semantic backend unavailable."
        )
        if member is not None:
            self.assistanceChanged.emit(f"{member.signature} - {member.description} | {fallback}")
        elif context == "sheet" and prefix:
            self.assistanceChanged.emit(f"No Sheet API member named {prefix}. {fallback}")
        else:
            self.assistanceChanged.emit(fallback)

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


def _completion_words() -> list[str]:
    return [
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "False",
        "finally",
        "for",
        "from",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "None",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "True",
        "try",
        "while",
        "with",
        "yield",
        "sheet",
        "display",
        "pd",
        "px",
    ]
