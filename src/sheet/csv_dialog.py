from collections.abc import Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from sheet.csv_io import CsvData


class CsvImportDialog(QDialog):
    def __init__(self, data: CsvData, destination: str, conflicts: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self.destination = QLineEdit(destination)
        self.overwrite = QCheckBox(f"Overwrite {conflicts} non-empty destination cell(s)")
        self.overwrite.setEnabled(conflicts > 0)
        self._build_ui(data)

    def _build_ui(self, data: CsvData) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"Detected UTF-8 CSV with {len(data.rows)} rows and {data.columns} columns.")
        )
        form = QFormLayout()
        form.addRow("Start at:", self.destination)
        layout.addLayout(form)
        layout.addWidget(self.overwrite)
        layout.addWidget(_preview(data.rows))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class CsvExportDialog(QDialog):
    def __init__(self, rows: Sequence[Sequence[str]], scope: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export CSV")
        self.values = QCheckBox("Export calculated display values instead of formulas")
        self._build_ui(rows, scope)

    def _build_ui(self, rows: Sequence[Sequence[str]], scope: str) -> None:
        layout = QVBoxLayout(self)
        columns = max((len(row) for row in rows), default=0)
        layout.addWidget(QLabel(f"Exporting {scope}: {len(rows)} rows and {columns} columns."))
        layout.addWidget(self.values)
        layout.addWidget(_preview(rows))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def _preview(rows: Sequence[Sequence[str]]) -> QTableWidget:
    preview_rows = list(rows[:10])
    columns = min(max((len(row) for row in preview_rows), default=0), 10)
    table = QTableWidget(len(preview_rows), columns)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setMaximumHeight(230)
    for row_index, row in enumerate(preview_rows):
        for column_index, value in enumerate(row[:columns]):
            table.setItem(row_index, column_index, QTableWidgetItem(value))
    return table
