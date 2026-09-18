from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QProgressDialog

from sheet.coordinates import cell_reference, parse_cell_reference
from sheet.csv_dialog import CsvExportDialog, CsvImportDialog
from sheet.csv_io import CsvCancelled, CsvData, CsvError, read_csv, write_csv
from sheet.csv_transfer import export_coordinates, export_rows, import_cells, import_conflict_count

if TYPE_CHECKING:
    from sheet.window import MainWindow


def import_csv(window: MainWindow) -> None:
    path, _ = QFileDialog.getOpenFileName(window, "Import CSV", "", "CSV files (*.csv)")
    if not path:
        return
    progress = csv_progress(window, "Reading CSV…")
    try:
        data = read_csv(path, progress_callback(progress))
    except CsvCancelled:
        window.statusBar().showMessage("CSV import cancelled", 2000)
        return
    except (OSError, CsvError) as error:
        QMessageBox.critical(window, "Could not import CSV", str(error))
        return
    finally:
        progress.close()
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
    progress = csv_progress(window, "Writing CSV…")
    try:
        write_csv(selected, rows, progress_callback(progress))
    except CsvCancelled:
        window.statusBar().showMessage("CSV export cancelled", 2000)
        return
    except OSError as error:
        QMessageBox.critical(window, "Could not export CSV", str(error))
        return
    finally:
        progress.close()
    window.statusBar().showMessage(f"Exported CSV to {selected.name}", 2500)


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


def progress_callback(progress: QProgressDialog):
    def callback(rows: int) -> bool:
        progress.setLabelText(f"{progress.windowTitle()} — {rows} rows")
        QApplication.processEvents()
        return not progress.wasCanceled()

    return callback


def _import_destination(window: MainWindow):
    current = window.table.currentIndex()
    if not current.isValid():
        window._select_first_cell()
        return window.table.currentIndex()
    return current
