from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QResizeEvent
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


class FrozenTableView(QTableView):
    def __init__(self) -> None:
        super().__init__()
        self._frozen_rows = 0
        self._frozen_columns = 0
        self._top: QTableView | None = None
        self._left: QTableView | None = None
        self._corner: QTableView | None = None
        self.horizontalScrollBar().valueChanged.connect(self._sync_horizontal_scroll)
        self.verticalScrollBar().valueChanged.connect(self._sync_vertical_scroll)

    def set_frozen_panes(self, rows: int, columns: int) -> None:
        self._frozen_rows = rows
        self._frozen_columns = columns
        self._ensure_overlays()
        self._configure_overlays()
        self._update_frozen_geometry()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_frozen_geometry()

    def _ensure_overlays(self) -> None:
        if self._top is not None or self.model() is None or self.selectionModel() is None:
            return
        self._top = self._make_overlay()
        self._left = self._make_overlay()
        self._corner = self._make_overlay()
        self.horizontalHeader().sectionResized.connect(lambda *_: self._update_frozen_geometry())
        self.verticalHeader().sectionResized.connect(lambda *_: self._update_frozen_geometry())

    def _make_overlay(self) -> QTableView:
        overlay = QTableView(self)
        overlay.setModel(self.model())
        overlay.setSelectionModel(self.selectionModel())
        overlay.setItemDelegate(self.itemDelegate())
        overlay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        overlay.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        overlay.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overlay.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overlay.horizontalHeader().hide()
        overlay.verticalHeader().hide()
        overlay.setStyleSheet("QTableView { border: none; }")
        return overlay

    def _configure_overlays(self) -> None:
        if self._top is None or self._left is None or self._corner is None:
            return
        for row in range(self.model().rowCount()):
            self._top.setRowHidden(row, row >= self._frozen_rows)
            self._left.setRowHidden(row, row < self._frozen_rows)
            self._corner.setRowHidden(row, row >= self._frozen_rows)
        for column in range(self.model().columnCount()):
            self._top.setColumnHidden(column, column < self._frozen_columns)
            self._left.setColumnHidden(column, column >= self._frozen_columns)
            self._corner.setColumnHidden(column, column >= self._frozen_columns)
        self._top.setVisible(self._frozen_rows > 0)
        self._left.setVisible(self._frozen_columns > 0)
        self._corner.setVisible(self._frozen_rows > 0 and self._frozen_columns > 0)

    def _update_frozen_geometry(self) -> None:
        if self._top is None or self._left is None or self._corner is None:
            return
        viewport = self.viewport().geometry()
        height = sum(self.rowHeight(row) for row in range(self._frozen_rows))
        width = sum(self.columnWidth(column) for column in range(self._frozen_columns))
        self._top.setGeometry(
            viewport.x() + width, viewport.y(), max(0, viewport.width() - width), height
        )
        self._left.setGeometry(
            viewport.x(), viewport.y() + height, width, max(0, viewport.height() - height)
        )
        self._corner.setGeometry(viewport.x(), viewport.y(), width, height)
        self._sync_horizontal_scroll(self.horizontalScrollBar().value())
        self._sync_vertical_scroll(self.verticalScrollBar().value())

    def _sync_horizontal_scroll(self, value: int) -> None:
        if self._top is not None:
            self._top.horizontalScrollBar().setValue(value)

    def _sync_vertical_scroll(self, value: int) -> None:
        if self._left is not None:
            self._left.verticalScrollBar().setValue(value)


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
    table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
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
    window.function_hint = QLabel()
    window.function_hint.setObjectName("functionHint")
    window.function_hint.setMinimumWidth(220)
    layout.addWidget(window.function_hint)
    window.formula_accept_button = QToolButton()
    window.formula_accept_button.setText("✓")
    window.formula_accept_button.setToolTip("Apply formula")
    window.formula_accept_button.clicked.connect(window._commit_formula_bar)
    layout.addWidget(window.formula_accept_button)
    window.formula_cancel_button = QToolButton()
    window.formula_cancel_button.setText("x")
    window.formula_cancel_button.setToolTip("Cancel formula editing (Escape)")
    window.formula_cancel_button.clicked.connect(window._cancel_formula_edit)
    layout.addWidget(window.formula_cancel_button)
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
