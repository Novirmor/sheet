from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog

from sheet.coordinates import cell_reference, parse_cell_reference
from sheet.csv_dialog import CsvExportDialog, CsvImportDialog
from sheet.csv_io import CsvData
from sheet.csv_transfer import export_coordinates, export_rows, import_cells, import_conflict_count
from sheet.csv_worker import CsvWorker

if TYPE_CHECKING:
    from sheet.window import MainWindow


class CsvJob(QObject):
    def __init__(
        self,
        window: MainWindow,
        progress: QProgressDialog,
        action,
        completed: Callable[[object], None],
    ) -> None:
        super().__init__(window)
        self.window = window
        self.progress = progress
        self.action = action
        self.completed_callback = completed

    @Slot(int)
    def report_progress(self, rows: int) -> None:
        self.progress.setLabelText(f"CSV — {rows} rows")

    @Slot(object)
    def completed(self, result: object) -> None:
        self.completed_callback(result)

    @Slot(str)
    def failed(self, error: str) -> None:
        QMessageBox.critical(self.window, "CSV error", error)

    @Slot()
    def cancelled(self) -> None:
        self.window.statusBar().showMessage("CSV operation cancelled", 2000)

    @Slot()
    def finish(self) -> None:
        self.progress.close()
        self.action.setEnabled(True)
        self.window.csv_thread = None
        self.window.csv_worker = None
        self.window.csv_job = None
        self.deleteLater()


def import_csv(window: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(window, "Import CSV", "", "CSV files (*.csv)")
    if not path:
        return
    _start_job(
        window,
        CsvWorker("read", Path(path)),
        "Reading CSV…",
        lambda data: _finish_import(window, cast(CsvData, data)),
        window.import_csv_action,
    )


def _finish_import(window: MainWindow, data: CsvData) -> None:
    if not data.rows:
        window.statusBar().showMessage("CSV file is empty", 2000)
        return
    current = _import_destination(window)
    dialog = CsvImportDialog(
        data,
        cell_reference(current.row(), current.column()),
        csv_conflicts(window, data, current.row(), current.column()),
        window,
    )
    if dialog.exec() != CsvImportDialog.DialogCode.Accepted:
        return
    try:
        start_row, start_column = parse_cell_reference(dialog.destination.text().strip())
    except ValueError:
        QMessageBox.warning(window, "Import CSV", "Enter a valid destination cell, such as A1.")
        return
    conflicts = csv_conflicts(window, data, start_row, start_column)
    if conflicts and not dialog.overwrite.isChecked():
        QMessageBox.warning(
            window, "Import CSV", "Enable overwrite to replace existing cell values."
        )
        return
    window.model.set_cells(import_cells(data.rows, start_row, start_column), "Import CSV")
    window._select_range(start_row, start_column, data.rows)
    window.statusBar().showMessage(f"Imported {len(data.rows)} CSV row(s)", 2500)


def export_csv(window: MainWindow) -> None:
    rows = csv_rows(window)
    if not rows:
        QMessageBox.information(window, "Export CSV", "There are no cells to export.")
        return
    dialog = CsvExportDialog(rows, csv_scope(window), window)
    if dialog.exec() != CsvExportDialog.DialogCode.Accepted:
        return
    if dialog.values.isChecked():
        rows = csv_rows(window, display_values=True)
    initial = (
        window.workbook.path.with_suffix(".csv") if window.workbook.path else Path("sheet.csv")
    )
    path, _ = QFileDialog.getSaveFileName(window, "Export CSV", str(initial), "CSV files (*.csv)")
    if not path:
        return
    selected = Path(path)
    if not selected.suffix:
        selected = selected.with_suffix(".csv")
    _start_job(
        window,
        CsvWorker("write", selected, rows),
        "Writing CSV…",
        lambda _: window.statusBar().showMessage(f"Exported CSV to {selected.name}", 2500),
        window.export_csv_action,
    )


def csv_rows(window: MainWindow, *, display_values: bool = False) -> list[list[str]]:
    selected = window._selected_indexes()
    coordinates = export_coordinates(
        ((index.row(), index.column()) for index in selected if index.isValid()),
        window.workbook.cells,
    )
    if display_values:
        return export_rows(
            coordinates,
            lambda row, column: str(window.model.data(window.model.index(row, column))),
        )
    return export_rows(coordinates, window.workbook.raw_value)


def csv_scope(window: MainWindow) -> str:
    selected = [index for index in window._selected_indexes() if index.isValid()]
    return "the selected range" if len(selected) > 1 else "the used range"


def csv_conflicts(window: MainWindow, data: CsvData, start_row: int, start_column: int) -> int:
    return import_conflict_count(data.rows, start_row, start_column, window.workbook.cells)


def csv_progress(window: MainWindow, label: str) -> QProgressDialog:
    progress = QProgressDialog(label, "Cancel", 0, 0, window)
    progress.setWindowTitle("CSV")
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.show()
    return progress


def _start_job(
    window: MainWindow,
    worker: CsvWorker,
    label: str,
    completed,
    action,
) -> None:
    if window.csv_thread is not None:
        return
    progress = csv_progress(window, label)
    thread = QThread(window)
    job = CsvJob(window, progress, action, completed)
    window.csv_thread = thread
    window.csv_worker = worker
    window.csv_job = job
    action.setEnabled(False)
    worker.moveToThread(thread)
    worker.progress.connect(job.report_progress)
    worker.completed.connect(job.completed)
    worker.failed.connect(job.failed)
    worker.cancelled.connect(job.cancelled)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(job.finish)
    progress.canceled.connect(worker.cancel)
    thread.started.connect(worker.run)
    thread.start()


def _import_destination(window: MainWindow):
    current = window.table.currentIndex()
    if not current.isValid():
        window._select_first_cell()
        return window.table.currentIndex()
    return current
