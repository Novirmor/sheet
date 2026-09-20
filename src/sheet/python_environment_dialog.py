"""Workspace UI for inspecting user-controlled Python environments."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from sheet.python_environment import (
    DependencyDeclaration,
    EnvironmentInspection,
    app_runtime_inspection,
    command_preview,
    dependency_declaration,
    find_uv,
    inspect_interpreter,
    reset_selected_interpreter,
    run_uv_operation,
    save_selected_interpreter,
    selected_interpreter,
    uv_operation,
)


class PythonEnvironmentDialog(QDialog):
    def __init__(self, workspace, parent=None) -> None:
        super().__init__(parent or workspace)
        self.setWindowTitle("Python environment")
        self.workspace = workspace
        self.settings = QSettings()
        self.inspection: EnvironmentInspection | None = None
        self._build_ui()
        self._show_current_environment()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "External environments are user-controlled, not security sandboxes. "
                "Validate an interpreter, then select it to run Sheet sessions with it."
            )
        )
        form = QFormLayout()
        self.path = QLineEdit()
        form.addRow("Interpreter", self.path)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addRow("Status", self.status)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumBlockCount(100)
        form.addRow("Probe", self.details)
        layout.addLayout(form)
        selection = QHBoxLayout()
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        selection.addWidget(browse)
        validate = QPushButton("Validate")
        validate.clicked.connect(self._validate)
        selection.addWidget(validate)
        self.use_button = QPushButton("Use validated interpreter")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self._use_validated)
        selection.addWidget(self.use_button)
        reset = QPushButton("Reset to application runtime")
        reset.clicked.connect(self._reset)
        selection.addWidget(reset)
        layout.addLayout(selection)
        dependencies = QHBoxLayout()
        export = QPushButton("Preview dependency declaration")
        export.clicked.connect(self._preview_declaration)
        dependencies.addWidget(export)
        self.uv_button = QPushButton("Create .venv and install with uv")
        self.uv_button.setEnabled(find_uv() is not None)
        self.uv_button.setToolTip(
            "Unavailable: uv was not found." if not self.uv_button.isEnabled() else ""
        )
        self.uv_button.clicked.connect(self._create_with_uv)
        dependencies.addWidget(self.uv_button)
        layout.addLayout(dependencies)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(
            "Operation logs appear here. No install runs without confirmation."
        )
        layout.addWidget(self.log)

    def _show_current_environment(self) -> None:
        selected = selected_interpreter(self.settings)
        if selected is None:
            self.path.setText(str(Path(app_runtime_inspection().path)))
            self.status.setText("Application runtime (default)")
        else:
            self.path.setText(str(selected))
            self.status.setText("Selected external interpreter. Validate before changing it.")

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select existing Python interpreter")
        if path:
            self.path.setText(path)
            self.inspection = None
            self.use_button.setEnabled(False)

    def _validate(self) -> None:
        self.inspection = inspect_interpreter(self.path.text())
        inspection = self.inspection
        details = [f"Path: {inspection.path}"]
        if inspection.executable:
            details.append(f"Executable: {inspection.executable}")
        if inspection.version:
            details.append("Python: " + ".".join(str(value) for value in inspection.version))
        for name, version in (inspection.packages or {}).items():
            details.append(f"{name}: {version or 'missing'}")
        if inspection.error:
            details.append(f"Error: {inspection.error}")
        elif not inspection.external_launch_available:
            details.append("Launch: unavailable in this build; reset to the application runtime.")
        else:
            details.append("Launch: available; new sessions will use this interpreter.")
        self.details.setPlainText("\n".join(details))
        self.status.setText(
            "Validated. Use it to run new sessions, or keep the application runtime."
            if inspection.compatible
            else inspection.error
        )
        self.use_button.setEnabled(inspection.compatible)

    def _use_validated(self) -> None:
        if self.inspection is None or not self.inspection.compatible:
            return
        save_selected_interpreter(self.settings, self.inspection.path)
        self.workspace.environment_changed(external=True)
        self.status.setText("External interpreter selected locally. New runs will launch with it.")

    def _reset(self) -> None:
        reset_selected_interpreter(self.settings)
        self.workspace.environment_changed(external=False)
        self.inspection = None
        self.use_button.setEnabled(False)
        self._show_current_environment()
        self.details.clear()

    def _choose_project(self) -> Path | None:
        directory = QFileDialog.getExistingDirectory(self, "Choose project directory")
        return Path(directory) if directory else None

    def _declaration(self, directory: Path) -> DependencyDeclaration | None:
        packages = (self.inspection or app_runtime_inspection()).packages or {}
        try:
            return dependency_declaration(directory, packages)
        except ValueError as error:
            QMessageBox.warning(self, "Dependency declaration", str(error))
            return None

    def _preview_declaration(self) -> None:
        directory = self._choose_project()
        if directory is None:
            return
        declaration = self._declaration(directory)
        if declaration is None:
            return
        action = "Overwrite" if declaration.exists else "Create"
        if (
            QMessageBox.question(
                self,
                "Preview dependency declaration",
                f"{action} {declaration.path}?\n\n{declaration.content}\n"
                "Sheet owns only this file and will not change project metadata "
                "or install packages.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        declaration.path.write_text(declaration.content, encoding="utf-8")
        self.log.setPlainText(f"Wrote portable dependency declaration: {declaration.path}")

    def _create_with_uv(self) -> None:
        directory = self._choose_project()
        if directory is None:
            return
        declaration = self._declaration(directory)
        uv = find_uv()
        if declaration is None or uv is None:
            self.log.setPlainText("uv is unavailable; no environment was created.")
            return
        operation = uv_operation(uv, directory, declaration)
        if (
            QMessageBox.question(
                self,
                "Confirm uv environment setup",
                f"Target: {operation.target}\n\nExact argv:\n"
                f"{command_preview(operation.commands)}\n\n"
                "This creates the target environment and installs the declaration "
                "only after you confirm.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if not declaration.path.exists():
            declaration.path.write_text(declaration.content, encoding="utf-8")
        result = run_uv_operation(operation)
        self.log.setPlainText(result.log or "uv completed without output.")
        if not result.succeeded:
            QMessageBox.warning(
                self, "uv environment setup failed", "See the operation log for details."
            )
