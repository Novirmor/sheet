import builtins
import traceback
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from sheet.model import SpreadsheetModel
from sheet.scripting import SheetAPI

STARTER_SCRIPT = """# The sheet API is available to this script.
# sheet.set("A1", 10)
# print(sheet.get("A1"))
# sheet.write("A1", [[1, 2], [3, 4]])
# print(sheet.range("A1:B2"))
"""


class ScriptDialog(QDialog):
    def __init__(self, model: SpreadsheetModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.script_path: Path | None = None
        self.editor = QPlainTextEdit(STARTER_SCRIPT)
        self.output = QPlainTextEdit()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Python script")
        self.resize(850, 650)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(QLabel("Python"))
        editor_layout.addWidget(self.editor)

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(QLabel("Output"))
        output_layout.addWidget(self.output)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(editor_panel)
        splitter.addWidget(output_panel)
        splitter.setSizes([430, 170])

        open_button = QPushButton("Open…")
        open_button.clicked.connect(self._open_script)
        save_button = QPushButton("Save…")
        save_button.clicked.connect(self._save_script)
        run_button = QPushButton("Run")
        run_button.setDefault(True)
        run_button.clicked.connect(self.run_script)
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(open_button)
        buttons.addWidget(save_button)
        buttons.addStretch()
        buttons.addWidget(run_button)
        buttons.addWidget(close_buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        layout.addLayout(buttons)

    def run_script(self) -> None:
        stream = StringIO()
        filename = str(self.script_path) if self.script_path else "<sheet-script>"
        namespace = {
            "__builtins__": builtins.__dict__,
            "__name__": "__sheet_script__",
            "sheet": SheetAPI(self.model.workbook),
        }
        with redirect_stdout(stream), redirect_stderr(stream):
            try:
                code = compile(self.editor.toPlainText(), filename, "exec")
                exec(code, namespace)
            except BaseException:
                traceback.print_exc()
        self.model.refresh()
        result = stream.getvalue()
        self.output.setPlainText(result if result else "Script finished successfully.")

    def _open_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Python script", "", "Python (*.py)")
        if not path:
            return
        try:
            self.editor.setPlainText(Path(path).read_text())
        except OSError as error:
            QMessageBox.critical(self, "Could not open script", str(error))
            return
        self.script_path = Path(path)

    def _save_script(self) -> None:
        initial = str(self.script_path) if self.script_path else "script.py"
        path, _ = QFileDialog.getSaveFileName(self, "Save Python script", initial, "Python (*.py)")
        if not path:
            return
        selected = Path(path)
        if not selected.suffix:
            selected = selected.with_suffix(".py")
        try:
            selected.write_text(self.editor.toPlainText())
        except OSError as error:
            QMessageBox.critical(self, "Could not save script", str(error))
            return
        self.script_path = selected
