from __future__ import annotations

from collections.abc import Container
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

if TYPE_CHECKING:
    from sheet.script_dialog import ScriptWorkspace


def new_script(workspace: ScriptWorkspace) -> None:
    name, accepted = QInputDialog.getText(workspace, "New script", "Script name:")
    name = name.strip()
    if not accepted or not name:
        return
    if name in workspace.model.workbook.scripts:
        QMessageBox.warning(workspace, "Script already exists", f'"{name}" already exists.')
        return
    workspace.sync_active_script()
    workspace.model.workbook.set_script(name, "")
    workspace._load_scripts(name)


def rename_script(workspace: ScriptWorkspace) -> None:
    if not workspace.active_name:
        return
    name, accepted = QInputDialog.getText(
        workspace, "Rename script", "Script name:", text=workspace.active_name
    )
    name = name.strip()
    if not accepted or not name or name == workspace.active_name:
        return
    if name in workspace.model.workbook.scripts:
        QMessageBox.warning(workspace, "Script already exists", f'"{name}" already exists.')
        return
    workspace.sync_active_script()
    source = workspace.model.workbook.scripts.get(
        workspace.active_name, workspace.editor.toPlainText()
    )
    workspace.model.workbook.set_script(name, source)
    workspace.model.workbook.delete_script(workspace.active_name)
    if path := workspace.external_paths.pop(workspace.active_name, None):
        workspace.external_paths[name] = path
    workspace._load_scripts(name)


def delete_script(workspace: ScriptWorkspace) -> None:
    if not workspace.active_name:
        return
    workspace.sync_active_script()
    workspace.model.workbook.delete_script(workspace.active_name)
    workspace.external_paths.pop(workspace.active_name, None)
    workspace._load_scripts()


def import_script(workspace: ScriptWorkspace) -> None:
    path, _ = QFileDialog.getOpenFileName(workspace, "Import Python script", "", "Python (*.py)")
    if not path:
        return
    selected = Path(path)
    try:
        source = selected.read_text()
    except OSError as error:
        QMessageBox.critical(workspace, "Could not import script", str(error))
        return
    workspace.sync_active_script()
    name = available_name(selected.stem or "script", workspace.model.workbook.scripts)
    workspace.model.workbook.set_script(name, source)
    workspace.external_paths[name] = selected
    workspace._load_scripts(name)


def export_script(workspace: ScriptWorkspace) -> None:
    workspace.sync_active_script()
    initial = str(
        workspace.external_paths.get(workspace.active_name, Path(f"{workspace.active_name}.py"))
    )
    path, _ = QFileDialog.getSaveFileName(
        workspace, "Export Python script", initial, "Python (*.py)"
    )
    if not path:
        return
    selected = Path(path).with_suffix(".py") if not Path(path).suffix else Path(path)
    try:
        selected.write_text(workspace.editor.toPlainText())
    except OSError as error:
        QMessageBox.critical(workspace, "Could not export script", str(error))
        return
    workspace.external_paths[workspace.active_name] = selected
    workspace._update_script_state()


def save_external_script(workspace: ScriptWorkspace) -> None:
    path = workspace.external_paths.get(workspace.active_name)
    if path is None:
        export_script(workspace)
        return
    workspace.sync_active_script()
    try:
        path.write_text(workspace.editor.toPlainText())
    except OSError as error:
        QMessageBox.critical(workspace, "Could not save external script", str(error))
        return
    workspace.output.setPlainText(f"Saved external script to {path}")


def reload_external_script(workspace: ScriptWorkspace) -> None:
    path = workspace.external_paths.get(workspace.active_name)
    if path is None:
        return
    try:
        source = path.read_text()
    except OSError as error:
        QMessageBox.critical(workspace, "Could not reload script", str(error))
        return
    workspace._set_editor_source(source)
    workspace._source_dirty = True
    workspace.sync_active_script()


def available_name(base: str, names: Container[str]) -> str:
    name = base
    suffix = 2
    while name in names:
        name = f"{base} {suffix}"
        suffix += 1
    return name
