from collections.abc import Callable

from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ScriptLibraryPanel(QWidget):
    def __init__(
        self,
        select_script: Callable[[str], None],
        new_script: Callable[[], None],
        rename_script: Callable[[], None],
        delete_script: Callable[[], None],
        import_script: Callable[[], None],
        export_script: Callable[[], None],
        save_external_script: Callable[[], None],
        reload_external_script: Callable[[], None],
    ) -> None:
        super().__init__()
        self.script_list = QListWidget()
        self.script_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.script_list.currentTextChanged.connect(select_script)
        self.new_button = _button("New", new_script)
        self.rename_button = _button("Rename", rename_script)
        self.delete_button = _button("Delete", delete_script)
        self.import_button = _button("Import…", import_script)
        self.export_button = _button("Export…", export_script)
        self.save_external_button = _button("Save external", save_external_script)
        self.reload_button = _button("Reload", reload_external_script)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Workbook scripts"))
        layout.addWidget(self.script_list)
        for button in (
            self.new_button,
            self.rename_button,
            self.delete_button,
            self.import_button,
            self.export_button,
            self.save_external_button,
            self.reload_button,
        ):
            layout.addWidget(button)

    def set_running(self, running: bool, has_external_file: bool) -> None:
        self.rename_button.setEnabled(not running)
        self.delete_button.setEnabled(not running)
        self.import_button.setEnabled(not running)
        self.export_button.setEnabled(not running)
        self.save_external_button.setEnabled(not running and has_external_file)
        self.reload_button.setEnabled(not running and has_external_file)
        self.script_list.setEnabled(not running)

    def set_external_actions(self, has_external_file: bool) -> None:
        self.reload_button.setEnabled(has_external_file)
        self.save_external_button.setEnabled(has_external_file)


def _button(text: str, callback: Callable[[], None]) -> QPushButton:
    button = QPushButton(text)
    button.clicked.connect(callback)
    return button
