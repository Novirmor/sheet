import sqlite3
from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStyle,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sheet.coordinates import cell_reference, parse_cell_reference
from sheet.model import SpreadsheetModel
from sheet.script_dialog import ScriptDialog
from sheet.workbook import Workbook


class MainWindow(QMainWindow):
    def __init__(self, path: str | Path = ":memory:") -> None:
        super().__init__()
        self.model = SpreadsheetModel(Workbook(path))
        self.table = QTableView()
        self.name_box = QLineEdit("A1")
        self.formula_bar = QLineEdit()
        self._updating_format_controls = False
        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._connect_signals()
        self._select_first_cell()
        self._update_title()

    @property
    def workbook(self) -> Workbook:
        return self.model.workbook

    def _build_ui(self) -> None:
        self.setObjectName("mainWindow")
        self.resize(1280, 780)
        self.setMinimumSize(760, 480)

        self.table.setObjectName("spreadsheet")
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.table.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked
            | QTableView.EditTrigger.EditKeyPressed
            | QTableView.EditTrigger.AnyKeyPressed
        )
        self.table.setTabKeyNavigation(True)
        self.table.setWordWrap(False)
        self.table.setCornerButtonEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.table.horizontalHeader().setDefaultSectionSize(112)
        self.table.horizontalHeader().setMinimumSectionSize(48)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(27)
        self.table.verticalHeader().setMinimumSectionSize(22)

        formula_frame = QFrame()
        formula_frame.setObjectName("formulaFrame")
        formula_layout = QHBoxLayout(formula_frame)
        formula_layout.setContentsMargins(8, 6, 8, 6)
        formula_layout.setSpacing(8)

        self.name_box.setObjectName("nameBox")
        self.name_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_box.setFixedWidth(82)
        self.name_box.setToolTip("Cell reference")
        formula_layout.addWidget(self.name_box)

        fx_label = QLabel("fx")
        fx_label.setObjectName("fxLabel")
        fx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fx_label.setFixedWidth(28)
        formula_layout.addWidget(fx_label)

        self.formula_bar.setObjectName("formulaBar")
        self.formula_bar.setPlaceholderText("Enter a value or formula, for example =SUM(A1:A5)")
        self.formula_bar.setClearButtonEnabled(True)
        formula_layout.addWidget(self.formula_bar)

        layout = QVBoxLayout()
        layout.addWidget(formula_frame)
        layout.addWidget(self.table)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.position_label = QLabel("A1")
        self.position_label.setObjectName("statusPosition")
        self.summary_label = QLabel("Ready")
        self.document_state_label = QLabel()
        self.document_state_label.setObjectName("documentState")
        self.statusBar().addWidget(self.position_label)
        self.statusBar().addPermanentWidget(self.summary_label)
        self.statusBar().addPermanentWidget(self.document_state_label)
        self.statusBar().setSizeGripEnabled(False)

    def _build_actions(self) -> None:
        style = self.style()
        self.new_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), "&New", self
        )
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.setStatusTip("Create a new spreadsheet")
        self.new_action.triggered.connect(self._new_file)

        self.open_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "&Open…", self
        )
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setStatusTip("Open a Sheet database")
        self.open_action.triggered.connect(self._open_file)

        self.save_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "&Save", self
        )
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self._save)

        self.save_as_action = QAction("Save &As…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self._save_as)

        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.close)

        self.undo_action = self.model.undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.redo_action = self.model.undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))

        self.cut_action = QAction("Cu&t", self)
        self.cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self.cut_action.triggered.connect(self._cut)
        self.copy_action = QAction("&Copy", self)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.triggered.connect(self._copy)
        self.paste_action = QAction("&Paste", self)
        self.paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self.paste_action.triggered.connect(self._paste)
        self.delete_action = QAction("Clear contents", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self._clear_selection)
        self.select_all_action = QAction("Select &All", self)
        self.select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.select_all_action.triggered.connect(self.table.selectAll)

        self.bold_action = QAction("Bold", self)
        self.bold_action.setToolTip("Bold (Ctrl+B)")
        self.bold_action.setShortcut(QKeySequence.StandardKey.Bold)
        self.bold_action.setCheckable(True)
        self.bold_action.toggled.connect(lambda checked: self._apply_format(bold=checked))
        self.italic_action = QAction("Italic", self)
        self.italic_action.setToolTip("Italic (Ctrl+I)")
        self.italic_action.setShortcut(QKeySequence.StandardKey.Italic)
        self.italic_action.setCheckable(True)
        self.italic_action.toggled.connect(lambda checked: self._apply_format(italic=checked))

        alignment_group = QActionGroup(self)
        alignment_group.setExclusive(True)
        self.alignment_actions: dict[str, QAction] = {}
        for alignment, label in (
            ("left", "Align left"),
            ("center", "Center"),
            ("right", "Align right"),
        ):
            action = QAction(label, self)
            action.setToolTip(label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked, selected=alignment: (
                    checked and self._apply_format(alignment=selected)
                )
            )
            alignment_group.addAction(action)
            self.alignment_actions[alignment] = action
        self.alignment_actions["left"].setChecked(True)

        self.add_rows_action = QAction("Add 10 rows", self)
        self.add_rows_action.triggered.connect(lambda: self.model.add_rows(10))
        self.add_columns_action = QAction("Add 5 columns", self)
        self.add_columns_action.triggered.connect(lambda: self.model.add_columns(5))

        self.script_action = QAction("Run Python script…", self)
        self.script_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.script_action.setShortcut("Ctrl+Shift+P")
        self.script_action.setStatusTip("Open the embedded Python editor")
        self.script_action.triggered.connect(self._show_script_dialog)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions(
            [self.new_action, self.open_action, self.save_action, self.save_as_action]
        )
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions(
            [
                self.cut_action,
                self.copy_action,
                self.paste_action,
                self.delete_action,
                self.select_all_action,
            ]
        )

        format_menu = self.menuBar().addMenu("F&ormat")
        format_menu.addActions([self.bold_action, self.italic_action])
        alignment_menu = format_menu.addMenu("Alignment")
        alignment_menu.addActions(list(self.alignment_actions.values()))

        sheet_menu = self.menuBar().addMenu("&Sheet")
        sheet_menu.addActions([self.add_rows_action, self.add_columns_action])

        python_menu = self.menuBar().addMenu("&Python")
        python_menu.addAction(self.script_action)

        self.view_menu = self.menuBar().addMenu("&View")

    def _build_toolbars(self) -> None:
        main_toolbar = QToolBar("Main", self)
        main_toolbar.setObjectName("mainToolbar")
        main_toolbar.setMovable(False)
        main_toolbar.setIconSize(QSize(19, 19))
        main_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        main_toolbar.addActions([self.new_action, self.open_action, self.save_action])
        main_toolbar.addSeparator()
        main_toolbar.addActions([self.undo_action, self.redo_action])
        main_toolbar.addSeparator()
        main_toolbar.addAction(self.script_action)
        self.addToolBar(main_toolbar)

        format_toolbar = QToolBar("Formatting", self)
        format_toolbar.setObjectName("formatToolbar")
        format_toolbar.setMovable(False)
        format_toolbar.setIconSize(QSize(19, 19))
        format_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        format_toolbar.addActions([self.bold_action, self.italic_action])
        bold_button = format_toolbar.widgetForAction(self.bold_action)
        italic_button = format_toolbar.widgetForAction(self.italic_action)
        if isinstance(bold_button, QToolButton):
            bold_button.setObjectName("boldButton")
            bold_button.setText("B")
        if isinstance(italic_button, QToolButton):
            italic_button.setObjectName("italicButton")
            italic_button.setText("I")
        format_toolbar.addSeparator()
        format_toolbar.addActions(list(self.alignment_actions.values()))
        format_toolbar.addSeparator()

        self.number_format = QComboBox()
        self.number_format.setObjectName("numberFormat")
        self.number_format.setToolTip("Number format")
        self.number_format.addItem("General", "general")
        self.number_format.addItem("Number", "number")
        self.number_format.addItem("Currency", "currency")
        self.number_format.addItem("Percent", "percent")
        self.number_format.currentIndexChanged.connect(self._number_format_changed)
        format_toolbar.addWidget(self.number_format)
        self.addToolBar(format_toolbar)

        self.view_menu.addAction(main_toolbar.toggleViewAction())
        self.view_menu.addAction(format_toolbar.toggleViewAction())

    def _connect_signals(self) -> None:
        selection_model = self.table.selectionModel()
        selection_model.currentChanged.connect(self._current_cell_changed)
        selection_model.selectionChanged.connect(self._selection_changed)
        self.formula_bar.returnPressed.connect(self._commit_formula_bar)
        self.name_box.returnPressed.connect(self._go_to_cell)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.model.dataChanged.connect(self._model_changed)
        self.model.modelReset.connect(self._model_changed)
        self.model.rowsInserted.connect(self._model_changed)
        self.model.columnsInserted.connect(self._model_changed)

    def _select_first_cell(self) -> None:
        index = self.model.index(0, 0)
        self.table.setCurrentIndex(index)
        self.table.selectionModel().select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def _current_cell_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        del previous
        if not current.isValid():
            return
        reference = cell_reference(current.row(), current.column())
        self.name_box.setText(reference)
        self.position_label.setText(reference)
        self.formula_bar.setText(self.workbook.raw_value(current.row(), current.column()))
        self._sync_format_controls(current)

    def _selection_changed(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        del selected, deselected
        indexes = self.table.selectionModel().selectedIndexes()
        numbers: list[float] = []
        for index in indexes:
            value = self.workbook.value(index.row(), index.column())
            if isinstance(value, int | float) and not isinstance(value, bool):
                numbers.append(float(value))
        if numbers:
            average = sum(numbers) / len(numbers)
            self.summary_label.setText(
                f"Count {len(numbers)}     Sum {sum(numbers):g}     Average {average:g}"
            )
        elif len(indexes) > 1:
            self.summary_label.setText(f"{len(indexes)} cells selected")
        else:
            self.summary_label.setText("Ready")

    def _model_changed(self, *args: object) -> None:
        del args
        current = self.table.currentIndex()
        if current.isValid():
            self.formula_bar.setText(self.workbook.raw_value(current.row(), current.column()))
            self._sync_format_controls(current)
        self._selection_changed(QItemSelection(), QItemSelection())
        self._update_title()

    def _commit_formula_bar(self) -> None:
        index = self.table.currentIndex()
        if index.isValid():
            self.model.setData(index, self.formula_bar.text())
            self.table.setFocus()

    def _go_to_cell(self) -> None:
        try:
            row, column = parse_cell_reference(self.name_box.text().strip())
        except ValueError:
            self.name_box.setText(
                cell_reference(self.table.currentIndex().row(), self.table.currentIndex().column())
            )
            return
        if row >= self.workbook.rows or column >= self.workbook.columns:
            self.model.resize(
                max(self.workbook.rows, row + 1),
                max(self.workbook.columns, column + 1),
                "Expand sheet",
            )
        index = self.model.index(row, column)
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
        self.table.setFocus()

    def _selected_indexes(self) -> list[QModelIndex]:
        indexes = self.table.selectionModel().selectedIndexes()
        return indexes if indexes else [self.table.currentIndex()]

    def _apply_format(self, **changes: object) -> None:
        if self._updating_format_controls:
            return
        indexes = [index for index in self._selected_indexes() if index.isValid()]
        self.model.apply_format(indexes, **changes)

    def _number_format_changed(self) -> None:
        number_format = self.number_format.currentData()
        if isinstance(number_format, str):
            self._apply_format(number_format=number_format)

    def _sync_format_controls(self, index: QModelIndex) -> None:
        cell_format = self.workbook.cell_format(index.row(), index.column())
        self._updating_format_controls = True
        self.bold_action.setChecked(cell_format.bold)
        self.italic_action.setChecked(cell_format.italic)
        alignment = cell_format.alignment
        if alignment == "general":
            value = self.workbook.value(index.row(), index.column())
            alignment = (
                "right"
                if isinstance(value, int | float) and not isinstance(value, bool)
                else "left"
            )
        self.alignment_actions[alignment].setChecked(True)
        format_index = self.number_format.findData(cell_format.number_format)
        self.number_format.setCurrentIndex(format_index)
        self._updating_format_controls = False

    def _copy(self) -> None:
        indexes = self._selected_indexes()
        if not indexes or not indexes[0].isValid():
            return
        minimum_row = min(index.row() for index in indexes)
        maximum_row = max(index.row() for index in indexes)
        minimum_column = min(index.column() for index in indexes)
        maximum_column = max(index.column() for index in indexes)
        selected = {(index.row(), index.column()) for index in indexes}
        lines = []
        for row in range(minimum_row, maximum_row + 1):
            fields = []
            for column in range(minimum_column, maximum_column + 1):
                value = self.workbook.raw_value(row, column) if (row, column) in selected else ""
                fields.append(value.replace("\t", " ").replace("\n", " "))
            lines.append("\t".join(fields))
        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage("Copied selection", 1800)

    def _cut(self) -> None:
        self._copy()
        self._clear_selection("Cut cells")

    def _paste(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            return
        current = self.table.currentIndex()
        if not current.isValid():
            return
        start_row = current.row()
        start_column = current.column()
        rows = text.splitlines() or [""]
        values: dict[tuple[int, int], str] = {}
        for row_offset, line in enumerate(rows):
            for column_offset, value in enumerate(line.split("\t")):
                values[(start_row + row_offset, start_column + column_offset)] = value
        self.model.set_cells(values, "Paste cells")
        current = self.model.index(start_row, start_column)
        bottom_right = self.model.index(
            start_row + len(rows) - 1,
            start_column + max(len(line.split("\t")) for line in rows) - 1,
        )
        selection = QItemSelection(current, bottom_right)
        self.table.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _clear_selection(self, text: str = "Clear cells") -> None:
        values = {
            (index.row(), index.column()): ""
            for index in self._selected_indexes()
            if index.isValid()
        }
        self.model.set_cells(values, text)

    def _show_context_menu(self, position: QPoint) -> None:
        menu = QMenu(self)
        menu.addActions([self.cut_action, self.copy_action, self.paste_action])
        menu.addSeparator()
        menu.addAction(self.delete_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _show_script_dialog(self) -> None:
        ScriptDialog(self.model, self).exec()
        if not self.table.currentIndex().isValid():
            self._select_first_cell()
        self._update_title()

    def _new_file(self) -> None:
        if self._maybe_save_changes():
            self._replace_workbook(Workbook(":memory:"))

    def _open_file(self) -> None:
        if not self._maybe_save_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open spreadsheet", str(Path.home()), "Sheet database (*.sheet *.db *.sqlite3)"
        )
        if not path:
            return
        try:
            workbook = Workbook(Path(path))
        except (OSError, sqlite3.Error) as error:
            QMessageBox.critical(self, "Could not open spreadsheet", str(error))
            return
        self._replace_workbook(workbook)

    def _save(self) -> bool:
        if self.workbook.path is None:
            return self._save_as()
        try:
            self.workbook.save()
        except (OSError, sqlite3.Error) as error:
            QMessageBox.critical(self, "Could not save spreadsheet", str(error))
            return False
        self._update_title()
        self.statusBar().showMessage("All changes saved", 2000)
        return True

    def _save_as(self) -> bool:
        path = self._choose_save_path()
        if path is None:
            return False
        try:
            self.workbook.save_as(path)
        except (OSError, sqlite3.Error) as error:
            QMessageBox.critical(self, "Could not save spreadsheet", str(error))
            return False
        self._update_title()
        self.statusBar().showMessage(f"Saved to {path}", 2500)
        return True

    def _choose_save_path(self) -> Path | None:
        initial = self.workbook.path or Path.home() / "untitled.sheet"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save spreadsheet", str(initial), "Sheet database (*.sheet)"
        )
        if not path:
            return None
        selected = Path(path)
        return selected if selected.suffix else selected.with_suffix(".sheet")

    def _maybe_save_changes(self) -> bool:
        if not self.workbook.dirty:
            return True
        location = self.workbook.path.name if self.workbook.path else "this spreadsheet"
        answer = QMessageBox.question(
            self,
            "Save spreadsheet?",
            f"Save changes to {location}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self._save_as()
        if answer == QMessageBox.StandardButton.Discard:
            self.workbook.discard_changes()
            return True
        return False

    def _replace_workbook(self, workbook: Workbook) -> None:
        previous = self.workbook
        self.model.replace_workbook(workbook)
        previous.close()
        self._select_first_cell()
        self._update_title()

    def _update_title(self) -> None:
        name = self.workbook.path.name if self.workbook.path else "Untitled"
        modified = " *" if self.workbook.dirty else ""
        self.setWindowTitle(f"{name}{modified} — Sheet")
        if self.workbook.recovery_error is not None:
            self.document_state_label.setText("Recovery unavailable")
        elif self.workbook.dirty:
            self.document_state_label.setText("Modified")
        else:
            self.document_state_label.setText("Saved")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._maybe_save_changes():
            event.ignore()
            return
        self.workbook.close()
        event.accept()
