from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from sheet.window import MainWindow


class CellEditorDelegate(QStyledItemDelegate):
    def updateEditorGeometry(
        self,
        editor: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        del index
        editor.setGeometry(option.rect)


def build_ui(window: MainWindow) -> None:
    window.setObjectName("mainWindow")
    window.resize(1280, 780)
    window.setMinimumSize(760, 480)
    _configure_table(window)
    _build_central_widget(window)
    _build_status_bar(window)


def _configure_table(window: MainWindow) -> None:
    table = window.table
    table.setObjectName("spreadsheet")
    table.setModel(window.model)
    table.setItemDelegate(CellEditorDelegate(table))
    table.setAlternatingRowColors(False)
    table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
    table.setEditTriggers(
        QTableView.EditTrigger.DoubleClicked
        | QTableView.EditTrigger.EditKeyPressed
        | QTableView.EditTrigger.AnyKeyPressed
    )
    table.setTabKeyNavigation(True)
    table.setWordWrap(False)
    table.setCornerButtonEnabled(True)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
    table.horizontalHeader().setDefaultSectionSize(112)
    table.horizontalHeader().setMinimumSectionSize(48)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setSectionsClickable(True)
    table.verticalHeader().setDefaultSectionSize(27)
    table.verticalHeader().setMinimumSectionSize(22)
    table.verticalHeader().setSectionsClickable(True)


def _build_central_widget(window: MainWindow) -> None:
    formula_frame = _formula_frame(window)
    layout = QVBoxLayout()
    layout.addWidget(formula_frame)
    layout.addWidget(window.table)
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)
    container = QWidget()
    container.setLayout(layout)
    window.setCentralWidget(container)


def _formula_frame(window: MainWindow) -> QFrame:
    frame = QFrame()
    frame.setObjectName("formulaFrame")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(8)
    window.name_box.setObjectName("nameBox")
    window.name_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.name_box.setFixedWidth(82)
    window.name_box.setToolTip("Cell reference")
    layout.addWidget(window.name_box)
    window.fx_button = QToolButton()
    window.fx_button.setObjectName("fxButton")
    window.fx_button.setText("fx")
    window.fx_button.setToolTip("Insert a function")
    window.fx_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    window.fx_button.setMenu(window._function_menu())
    layout.addWidget(window.fx_button)
    window.formula_bar.setObjectName("formulaBar")
    window.formula_bar.setPlaceholderText("Enter a value or formula, for example =SUM(A1:A5)")
    window.formula_bar.setClearButtonEnabled(True)
    layout.addWidget(window.formula_bar)
    return frame


def _build_status_bar(window: MainWindow) -> None:
    window.position_label = QLabel("A1")
    window.position_label.setObjectName("statusPosition")
    window.summary_label = QLabel("Ready")
    window.document_state_label = QLabel()
    window.document_state_label.setObjectName("documentState")
    window.statusBar().addWidget(window.position_label)
    window.statusBar().addPermanentWidget(window.summary_label)
    window.statusBar().addPermanentWidget(window.document_state_label)
    window.statusBar().setSizeGripEnabled(False)
