from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    QModelIndex,
    QObject,
    QPoint,
    Qt,
)
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QProgressDialog,
    QTableView,
    QToolButton,
)

from sheet.clipboard import copy_text, paste_rows
from sheet.csv_io import CsvData
from sheet.csv_transfer import import_cells
from sheet.find_dialog import FindReplaceDialog
from sheet.model import SpreadsheetModel
from sheet.script_dialog import ScriptWorkspace
from sheet.window_actions import build_actions
from sheet.window_chrome import build_menus, build_toolbars
from sheet.window_csv import (
    csv_conflicts,
    csv_progress,
    csv_rows,
    csv_scope,
    export_csv,
    import_csv,
    progress_callback,
)
from sheet.window_document import NATIVE_FILE_FILTER as NATIVE_FILE_FILTER
from sheet.window_document import (
    choose_save_path,
    maybe_save_changes,
    new_file,
    open_file,
    replace_workbook,
    save,
    save_as,
    update_title,
)
from sheet.window_find import (
    find_next,
    matches,
    replace_all,
    replace_next,
    replace_value,
    show_find_replace,
)
from sheet.window_interaction import (
    apply_format,
    begin_formula_reference,
    commit_formula_bar,
    current_cell_changed,
    focus_cell,
    function_menu,
    go_to_cell,
    insert_formula_reference,
    insert_function,
    model_changed,
    number_format_changed,
    select_column,
    select_first_cell,
    select_range,
    select_row,
    selected_indexes,
    selection_changed,
    start_formula_reference_from_bar,
    stop_formula_reference,
    sync_format_controls,
)
from sheet.window_layout import CellEditorDelegate as CellEditorDelegate
from sheet.window_layout import build_ui
from sheet.window_structure import (
    delete_columns,
    delete_rows,
    insert_columns,
    insert_rows,
    selected_columns,
    selected_rows,
    selected_sections,
    sort_selection,
)
from sheet.workbook import Workbook


class MainWindow(QMainWindow):
    new_action: QAction
    open_action: QAction
    save_action: QAction
    save_as_action: QAction
    import_csv_action: QAction
    export_csv_action: QAction
    quit_action: QAction
    undo_action: QAction
    redo_action: QAction
    cut_action: QAction
    copy_action: QAction
    paste_action: QAction
    delete_action: QAction
    select_all_action: QAction
    find_replace_action: QAction
    bold_action: QAction
    italic_action: QAction
    alignment_actions: dict[str, QAction]
    add_rows_action: QAction
    add_columns_action: QAction
    insert_rows_action: QAction
    delete_rows_action: QAction
    insert_columns_action: QAction
    delete_columns_action: QAction
    sort_ascending_action: QAction
    sort_descending_action: QAction
    script_action: QAction
    view_menu: QMenu
    number_format: QComboBox
    find_dialog: FindReplaceDialog
    fx_button: QToolButton
    position_label: QLabel
    summary_label: QLabel
    document_state_label: QLabel

    def __init__(self, path: str | Path = ":memory:") -> None:
        super().__init__()
        self.model = SpreadsheetModel(Workbook(path))
        self.table = QTableView()
        self.name_box = QLineEdit("A1")
        self.formula_bar = QLineEdit()
        self._updating_format_controls = False
        self._formula_reference_prefix: str | None = None
        self._formula_reference_suffix = ""
        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self.script_workspace = ScriptWorkspace(self.model, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.script_workspace)
        self.script_workspace.hide()
        self.view_menu.addAction(self.script_workspace.toggleViewAction())
        self._connect_signals()
        self._select_first_cell()
        self._update_title()

    @property
    def workbook(self) -> Workbook:
        return self.model.workbook

    def _build_ui(self) -> None:
        build_ui(self)

    def _build_actions(self) -> None:
        build_actions(self)

    def _build_menus(self) -> None:
        build_menus(self)

    def _build_toolbars(self) -> None:
        build_toolbars(self)

    def _connect_signals(self) -> None:
        selection_model = self.table.selectionModel()
        selection_model.currentChanged.connect(self._current_cell_changed)
        selection_model.selectionChanged.connect(self._selection_changed)
        self.formula_bar.returnPressed.connect(self._commit_formula_bar)
        self.name_box.returnPressed.connect(self._go_to_cell)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.viewport().installEventFilter(self)
        self.table.horizontalHeader().sectionClicked.connect(self._select_column)
        self.table.verticalHeader().sectionClicked.connect(self._select_row)
        self.model.dataChanged.connect(self._model_changed)
        self.model.modelReset.connect(self._model_changed)
        self.model.rowsInserted.connect(self._model_changed)
        self.model.columnsInserted.connect(self._model_changed)

    def _select_first_cell(self) -> None:
        select_first_cell(self)

    def _select_row(self, row: int) -> None:
        select_row(self, row)

    def _select_column(self, column: int) -> None:
        select_column(self, column)

    def _current_cell_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        current_cell_changed(self, current, previous)

    def _selection_changed(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        selection_changed(self, selected, deselected)

    def _model_changed(self, *args: object) -> None:
        model_changed(self, *args)

    def _commit_formula_bar(self) -> None:
        commit_formula_bar(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.table.viewport():
            if event.type() == QEvent.Type.MouseButtonPress and self.formula_bar.hasFocus():
                self._start_formula_reference_from_bar()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._stop_formula_reference()
        return super().eventFilter(watched, event)

    def _function_menu(self) -> QMenu:
        return function_menu(self)

    def _insert_function(self, function: str) -> None:
        insert_function(self, function)

    def _start_formula_reference_from_bar(self) -> None:
        start_formula_reference_from_bar(self)

    def _begin_formula_reference(self, prefix: str, suffix: str) -> None:
        begin_formula_reference(self, prefix, suffix)

    def _insert_formula_reference(self, indexes: list[QModelIndex]) -> None:
        insert_formula_reference(self, indexes)

    def _stop_formula_reference(self) -> None:
        stop_formula_reference(self)

    def _go_to_cell(self) -> None:
        go_to_cell(self)

    def _selected_indexes(self) -> list[QModelIndex]:
        return selected_indexes(self)

    def _apply_format(self, **changes: object) -> None:
        apply_format(self, **changes)

    def _number_format_changed(self) -> None:
        number_format_changed(self)

    def _sync_format_controls(self, index: QModelIndex) -> None:
        sync_format_controls(self, index)

    def _copy(self) -> None:
        indexes = self._selected_indexes()
        if not indexes or not indexes[0].isValid():
            return
        text = copy_text(
            ((index.row(), index.column()) for index in indexes), self.workbook.raw_value
        )
        QApplication.clipboard().setText(text)
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
        rows = paste_rows(text)
        values = import_cells(rows, start_row, start_column)
        self.model.set_cells(values, "Paste cells")
        self._select_range(start_row, start_column, rows)

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
        self.script_workspace.show()
        self.script_workspace.raise_()

    def _insert_rows(self) -> None:
        insert_rows(self)

    def _delete_rows(self) -> None:
        delete_rows(self)

    def _insert_columns(self) -> None:
        insert_columns(self)

    def _delete_columns(self) -> None:
        delete_columns(self)

    def _sort_selection(self, *, descending: bool) -> None:
        sort_selection(self, descending=descending)

    def _show_find_replace(self) -> None:
        show_find_replace(self)

    def _find_next(self, search: str, match_case: bool) -> bool:
        return find_next(self, search, match_case)

    def _replace_next(self, search: str, replacement: str, match_case: bool) -> bool:
        return replace_next(self, search, replacement, match_case)

    def _replace_all(self, search: str, replacement: str, match_case: bool) -> int:
        return replace_all(self, search, replacement, match_case)

    @staticmethod
    def _matches(value: str, search: str, match_case: bool) -> bool:
        return matches(value, search, match_case)

    @staticmethod
    def _replace_value(value: str, search: str, replacement: str, match_case: bool) -> str:
        return replace_value(value, search, replacement, match_case)

    def _focus_cell(self, row: int, column: int) -> None:
        focus_cell(self, row, column)

    def _selected_rows(self) -> list[int]:
        return selected_rows(self)

    def _selected_columns(self) -> list[int]:
        return selected_columns(self)

    def _selected_sections(self, section) -> list[int]:
        return selected_sections(self, section)

    def _import_csv(self) -> None:
        import_csv(self)

    def _export_csv(self) -> None:
        export_csv(self)

    def _csv_rows(self, *, display_values: bool = False) -> list[list[str]]:
        return csv_rows(self, display_values=display_values)

    def _csv_scope(self) -> str:
        return csv_scope(self)

    def _csv_conflicts(self, data: CsvData, start_row: int, start_column: int) -> int:
        return csv_conflicts(self, data, start_row, start_column)

    def _csv_progress(self, label: str) -> QProgressDialog:
        return csv_progress(self, label)

    @staticmethod
    def _progress_callback(progress: QProgressDialog):
        return progress_callback(progress)

    def _select_range(self, start_row: int, start_column: int, rows: list[list[str]]) -> None:
        select_range(self, start_row, start_column, rows)

    def _new_file(self) -> None:
        new_file(self)

    def _open_file(self) -> None:
        open_file(self)

    def _save(self) -> bool:
        return save(self)

    def _save_as(self) -> bool:
        return save_as(self)

    def _choose_save_path(self) -> Path | None:
        return choose_save_path(self)

    def _maybe_save_changes(self) -> bool:
        return maybe_save_changes(self)

    def _replace_workbook(self, workbook: Workbook) -> None:
        replace_workbook(self, workbook)

    def _update_title(self) -> None:
        update_title(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._maybe_save_changes():
            event.ignore()
            return
        self.script_workspace.stop_script()
        self.workbook.close()
        event.accept()
