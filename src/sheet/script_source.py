from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sheet.code_editor import CodeEditor


class ScriptSourcePanel(QWidget):
    def __init__(
        self,
        editor: CodeEditor,
        find_next: Callable[[], None],
        search_library: Callable[[], None],
        open_outline: Callable[[int], None],
        toggle_fold: Callable[[], None],
        unfold_all: Callable[[], None],
        go_to_definition: Callable[[], None],
        find_references: Callable[[], None],
        rename_symbol: Callable[[], None],
        go_back: Callable[[], None],
        go_forward: Callable[[], None],
    ) -> None:
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

        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Search stored scripts")
        self.library_search.returnPressed.connect(search_library)
        self.case_sensitive = QCheckBox("Case")
        self.whole_word = QCheckBox("Word")
        library_button = QPushButton("Search library")
        library_button.clicked.connect(search_library)
        library_layout = QHBoxLayout()
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.addWidget(self.library_search)
        library_layout.addWidget(self.case_sensitive)
        library_layout.addWidget(self.whole_word)
        library_layout.addWidget(library_button)

        self.outline = QListWidget()
        self.outline.setMaximumHeight(105)
        self.outline.itemActivated.connect(lambda item: open_outline(int(item.data(32))))
        self.library_results = QListWidget()
        self.library_results.setMaximumHeight(105)
        fold_button = QPushButton("Fold current")
        fold_button.clicked.connect(toggle_fold)
        unfold_button = QPushButton("Unfold all")
        unfold_button.clicked.connect(unfold_all)
        outline_layout = QHBoxLayout()
        outline_layout.setContentsMargins(0, 0, 0, 0)
        outline_layout.addWidget(QLabel("Outline"))
        outline_layout.addStretch()
        outline_layout.addWidget(fold_button)
        outline_layout.addWidget(unfold_button)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        navigation_menu = QMenu(self)
        navigation_menu.addAction("Back", go_back)
        navigation_menu.addAction("Forward", go_forward)
        navigation_menu.addSeparator()
        navigation_menu.addAction("Go to definition", go_to_definition)
        navigation_menu.addAction("Find references", find_references)
        navigation_menu.addAction("Rename Python symbol", rename_symbol)
        navigation = QToolButton()
        navigation.setText("Navigate")
        navigation.setMenu(navigation_menu)
        navigation.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(navigation)
        header.addWidget(self.position)
        self.diagnostics = QLabel()
        self.diagnostics.setStyleSheet("color: #b42318")
        self.assistance = QLabel(
            "AST local/module navigation is available. Optional semantic backend unavailable."
        )
        self.assistance.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addLayout(find_layout)
        layout.addLayout(library_layout)
        layout.addWidget(self.library_results)
        layout.addLayout(outline_layout)
        layout.addWidget(self.outline)
        layout.addWidget(self.diagnostics)
        layout.addWidget(self.assistance)
        layout.addWidget(editor)
