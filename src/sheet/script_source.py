from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from sheet.code_editor import CodeEditor


class ScriptSourcePanel(QWidget):
    def __init__(self, editor: CodeEditor, find_next: Callable[[], None]) -> None:
        super().__init__()
        self.title = QLabel()
        self.position = QLabel()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find in script")
        self.search.returnPressed.connect(find_next)

        find_button = QPushButton("Find next")
        find_button.clicked.connect(find_next)
        find_layout = QHBoxLayout()
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.addWidget(self.search)
        find_layout.addWidget(find_button)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.position)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addLayout(find_layout)
        layout.addWidget(editor)
