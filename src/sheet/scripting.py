import builtins
import multiprocessing
import queue
import sys
import traceback
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any

from sheet.coordinates import cells_in_range, parse_cell_reference
from sheet.formulas import CellValue
from sheet.workbook import Workbook


class SheetAPI:
    def __init__(self, workbook: Workbook) -> None:
        self._workbook = workbook

    @property
    def rows(self) -> int:
        return self._workbook.rows

    @property
    def columns(self) -> int:
        return self._workbook.columns

    def get(self, reference: str) -> CellValue:
        row, column = parse_cell_reference(reference)
        return self._workbook.value(row, column)

    def raw(self, reference: str) -> str:
        row, column = parse_cell_reference(reference)
        return self._workbook.raw_value(row, column)

    def set(self, reference: str, value: Any) -> None:
        row, column = parse_cell_reference(reference)
        self._workbook.set_cell(row, column, "" if value is None else str(value))

    def clear(self, reference_range: str) -> None:
        values = {coordinate: "" for coordinate in self._range_coordinates(reference_range)}
        self._workbook.set_cells(values)

    def range(self, reference_range: str) -> list[list[CellValue]]:
        coordinates = list(self._range_coordinates(reference_range))
        if not coordinates:
            return []
        rows = sorted({row for row, _ in coordinates})
        columns = sorted({column for _, column in coordinates})
        return [[self._workbook.value(row, column) for column in columns] for row in rows]

    def write(self, start: str, values: Sequence[Sequence[Any]]) -> None:
        start_row, start_column = parse_cell_reference(start)
        updates = {
            (start_row + row_offset, start_column + column_offset): ""
            if value is None
            else str(value)
            for row_offset, row_values in enumerate(values)
            for column_offset, value in enumerate(row_values)
        }
        self._workbook.set_cells(updates)

    @staticmethod
    def _range_coordinates(reference_range: str):
        start, separator, end = reference_range.upper().partition(":")
        return cells_in_range(start, end if separator else start)


@dataclass(frozen=True, slots=True)
class ScriptResult:
    output: str
    changes: dict[tuple[int, int], str]
    rows: int
    columns: int
    failed: bool = False


def _script_worker(
    source: str,
    cells: dict[tuple[int, int], str],
    rows: int,
    columns: int,
    script_path: str | None,
    result_queue: Queue[ScriptResult],
) -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    workbook.resize(rows, columns)
    workbook.set_cells(cells)
    original_cells = dict(workbook.cells)
    stream = StringIO()
    namespace = {
        "__builtins__": builtins.__dict__,
        "__name__": "__sheet_script__",
        "sheet": SheetAPI(workbook),
    }
    filename = "<sheet-script>"
    if script_path is not None:
        filename = script_path
        sys.path.insert(0, str(Path(script_path).parent))
        namespace["__file__"] = script_path
    failed = False
    with redirect_stdout(stream), redirect_stderr(stream):
        try:
            exec(compile(source, filename, "exec"), namespace)
        except BaseException:
            failed = True
            traceback.print_exc()
    changes = {
        coordinate: workbook.raw_value(*coordinate)
        for coordinate in set(original_cells) | set(workbook.cells)
        if original_cells.get(coordinate, "") != workbook.raw_value(*coordinate)
    }
    result_queue.put(
        ScriptResult(stream.getvalue(), changes, workbook.rows, workbook.columns, failed)
    )
    workbook.close()


class ScriptProcess:
    def __init__(self, source: str, workbook: Workbook, script_path: str | None = None) -> None:
        context = multiprocessing.get_context("spawn")
        self._queue: Queue[ScriptResult] = context.Queue()
        self._process = context.Process(
            target=_script_worker,
            args=(
                source,
                dict(workbook.cells),
                workbook.rows,
                workbook.columns,
                script_path,
                self._queue,
            ),
        )

    @property
    def running(self) -> bool:
        return self._process.is_alive()

    def start(self) -> None:
        self._process.start()

    def poll(self) -> ScriptResult | None:
        try:
            result = self._queue.get_nowait()
        except queue.Empty:
            return None
        self._process.join(timeout=1)
        self._queue.close()
        return result

    def stop(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(timeout=1)
        self._queue.close()
