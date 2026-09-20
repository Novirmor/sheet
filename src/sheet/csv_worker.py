from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from sheet.csv_io import CsvCancelled, CsvError, read_csv, write_csv


class CsvWorker(QObject):
    progress = Signal(int)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(
        self, operation: str, path: Path, rows: Iterable[Iterable[str]] | None = None
    ) -> None:
        super().__init__()
        self.operation = operation
        self.path = path
        self.rows = list(rows) if rows is not None else None
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            if self.operation == "read":
                self.completed.emit(read_csv(self.path, self._report_progress))
            elif self.operation == "write" and self.rows is not None:
                write_csv(self.path, self.rows, self._report_progress)
                self.completed.emit(None)
            else:
                self.failed.emit("Unsupported CSV operation")
        except CsvCancelled:
            self.cancelled.emit()
        except (OSError, CsvError) as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

    def _report_progress(self, rows: int) -> bool:
        self.progress.emit(rows)
        return not self._cancelled.is_set()
