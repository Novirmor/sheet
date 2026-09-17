from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class FindReplaceDialog(QDialog):
    def __init__(
        self,
        find_next: Callable[[str, bool], bool],
        replace_next: Callable[[str, str, bool], bool],
        replace_all: Callable[[str, str, bool], int],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        self._find_next = find_next
        self._replace_next = replace_next
        self._replace_all = replace_all
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find entered values and formulas")
        self.replace_input = QLineEdit()
        self.case_sensitive = QCheckBox("Match case")
        self._build_ui()

    def _build_ui(self) -> None:
        form = QFormLayout()
        form.addRow("Find:", self.find_input)
        form.addRow("Replace with:", self.replace_input)

        find_button = QPushButton("Find next")
        find_button.clicked.connect(self._find)
        replace_button = QPushButton("Replace")
        replace_button.clicked.connect(self._replace)
        replace_all_button = QPushButton("Replace all")
        replace_all_button.clicked.connect(self._replace_everything)
        actions = QHBoxLayout()
        actions.addWidget(find_button)
        actions.addWidget(replace_button)
        actions.addWidget(replace_all_button)

        close_button = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_button.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.case_sensitive)
        layout.addLayout(actions)
        layout.addWidget(close_button)
        self.find_input.returnPressed.connect(self._find)

    def _find(self) -> None:
        self._find_next(self.find_input.text(), self.case_sensitive.isChecked())

    def _replace(self) -> None:
        self._replace_next(
            self.find_input.text(), self.replace_input.text(), self.case_sensitive.isChecked()
        )

    def _replace_everything(self) -> None:
        self._replace_all(
            self.find_input.text(), self.replace_input.text(), self.case_sensitive.isChecked()
        )
