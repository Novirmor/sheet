"""Python execution workers.

The persistent-session protocol uses plain dictionaries over multiprocessing queues:
``ready`` and ``result`` messages flow from child to parent, and ``execute`` and
``shutdown`` messages flow to the child. Every execute/result pair carries the
session, run, source, document, and snapshot identities so late replies are safe
to discard.
"""

import ast
import builtins
import multiprocessing
import queue
import sys
import time
import traceback
import uuid
from collections.abc import Callable, Mapping, Sequence, Sized
from contextlib import redirect_stderr, redirect_stdout, suppress
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from io import StringIO
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from numbers import Number
from pathlib import Path
from typing import Any

from sheet.coordinates import cells_in_range, parse_cell_reference
from sheet.formulas import CellValue
from sheet.workbook import Workbook


class SheetAPI:
    def __init__(self, workbook: Workbook) -> None:
        self._workbook = workbook

    def rebind(self, workbook: Workbook) -> None:
        """Point this stable API object at the current command's snapshot."""
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
        self._workbook.set_cell(row, column, _cell_input(value))

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
        updates = _write_updates(start_row, start_column, values)
        self._workbook.set_cells(updates)

    def dataframe(self, reference_range: str, *, headers: bool = True):
        import pandas as pd

        values = self.range(reference_range)
        if not values:
            return pd.DataFrame()
        if headers:
            return pd.DataFrame(values[1:], columns=values[0])
        return pd.DataFrame(values)

    def write_dataframe(
        self, start: str, dataframe, *, include_header: bool = True, include_index: bool = False
    ) -> None:
        rows = dataframe.to_numpy().tolist()
        if include_index:
            rows = [
                [str(index), *values]
                for index, values in zip(dataframe.index.tolist(), rows, strict=True)
            ]
        if include_header:
            rows.insert(
                0, ["index", *dataframe.columns] if include_index else list(dataframe.columns)
            )
        self.write(start, rows)

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
    document_id: str = ""
    snapshot_revision: int = 0
    run_id: str = ""
    stdout: str = ""
    stderr: str = ""
    exception: ExceptionInfo | None = None
    displays: tuple[DisplayResult, ...] = ()
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class OutputEvent:
    run_id: str
    channel: str
    sequence: int
    text: str


@dataclass(frozen=True, slots=True)
class ExceptionFrame:
    filename: str
    line: int
    function: str
    source_id: str = ""
    source_version: int = 0


@dataclass(frozen=True, slots=True)
class ExceptionInfo:
    type_name: str
    message: str
    frames: tuple[ExceptionFrame, ...]


@dataclass(frozen=True, slots=True)
class DisplayResult:
    kind: str
    text: str = ""
    columns: tuple[str, ...] = ()
    index: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    partial: bool = False


@dataclass(frozen=True, slots=True)
class VariableInfo:
    name: str
    type_name: str
    summary: str
    handle: str
    rows: int = 0
    columns: int = 0


@dataclass(frozen=True, slots=True)
class VariablePage:
    handle: str
    columns: tuple[str, ...]
    dtypes: tuple[str, ...]
    index: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    total_rows: int
    total_columns: int
    partial: bool
    missing: tuple[int, ...] = ()
    start: int = 0
    sheet_rows: tuple[tuple[str, ...], ...] = ()
    write_error: str = ""


@dataclass(frozen=True, slots=True)
class SessionInspection:
    request_id: str
    session_id: str
    variables: tuple[VariableInfo, ...] = ()
    page: VariablePage | None = None
    error: str = ""


def _cell_input(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str | bool | int):
        return str(value)
    if isinstance(value, float):
        return "" if value != value else str(value)
    if isinstance(value, Number) and not isinstance(value, complex):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    raise TypeError(f"unsupported cell value type: {type(value).__name__}")


def _write_updates(
    start_row: int, start_column: int, values: Sequence[Sequence[Any]]
) -> dict[tuple[int, int], str]:
    if isinstance(values, str | bytes) or not isinstance(values, Sequence):
        raise TypeError("values must be a sequence of row sequences")
    updates: dict[tuple[int, int], str] = {}
    width: int | None = None
    for row_offset, row_values in enumerate(values):
        if isinstance(row_values, str | bytes) or not isinstance(row_values, Sequence):
            raise TypeError(f"row {row_offset + 1} must be a sequence")
        if width is None:
            width = len(row_values)
        elif len(row_values) != width:
            raise ValueError("values must form a rectangular table")
        for column_offset, value in enumerate(row_values):
            updates[(start_row + row_offset, start_column + column_offset)] = _cell_input(value)
    return updates


def _script_worker(
    source: str,
    cells: dict[tuple[int, int], str],
    rows: int,
    columns: int,
    script_path: str | None,
    document_id: str,
    snapshot_revision: int,
    run_id: str,
    source_id: str,
    source_version: int,
    result_queue: Queue[ScriptResult],
) -> None:
    workbook = Workbook(":memory:", recovery_enabled=False)
    workbook.resize(rows, columns)
    workbook.set_cells(cells)
    original_cells = dict(workbook.cells)
    stdout = _BoundedStream()
    stderr = _BoundedStream()
    import pandas as pd
    import plotly.express as px

    namespace = {
        "__builtins__": builtins.__dict__,
        "__name__": "__sheet_script__",
        "sheet": SheetAPI(workbook),
        "pd": pd,
        "px": px,
    }
    displays: list[DisplayResult] = []
    namespace["display"] = lambda value: _display_value(value, displays)
    filename = "<sheet-script>"
    if script_path is not None:
        filename = script_path
        sys.path.insert(0, str(Path(script_path).parent))
        namespace["__file__"] = script_path
    failed = False
    exception: ExceptionInfo | None = None
    started = time.monotonic()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            exec(compile(source, filename, "exec"), namespace)
        except BaseException as error:
            failed = True
            command = SessionCommand(
                source,
                source_id,
                source_version,
                document_id,
                snapshot_revision,
                run_id,
                "",
                {},
                rows,
                columns,
                script_path=script_path,
            )
            exception = _exception_info(error, command)
            traceback.print_exc()
    changes = {
        coordinate: workbook.raw_value(*coordinate)
        for coordinate in set(original_cells) | set(workbook.cells)
        if original_cells.get(coordinate, "") != workbook.raw_value(*coordinate)
    }
    result_queue.put(
        ScriptResult(
            stdout.output() + stderr.output(),
            changes,
            workbook.rows,
            workbook.columns,
            failed,
            document_id,
            snapshot_revision,
            run_id,
            stdout.output(),
            stderr.output(),
            exception,
            tuple(displays),
            int((time.monotonic() - started) * 1000),
        )
    )
    workbook.close()


class ScriptProcess:
    def __init__(
        self,
        source: str,
        workbook: Workbook,
        script_path: str | None = None,
        *,
        source_id: str = "script",
        source_version: int = 0,
    ) -> None:
        context = multiprocessing.get_context("spawn")
        self.document_id = workbook.document_id
        self.snapshot_revision = workbook.revision
        self.run_id = uuid.uuid4().hex
        self._rows = workbook.rows
        self._columns = workbook.columns
        self._closed = False
        self._queue: Queue[ScriptResult] = context.Queue()
        self._process = context.Process(
            target=_script_worker,
            args=(
                source,
                dict(workbook.cells),
                workbook.rows,
                workbook.columns,
                script_path,
                self.document_id,
                self.snapshot_revision,
                self.run_id,
                source_id,
                source_version,
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
            if not self._process.is_alive() and not self._closed:
                try:
                    result = self._queue.get(timeout=0.1)
                except queue.Empty:
                    result = ScriptResult(
                        "Script process exited without returning a result.",
                        {},
                        self._rows,
                        self._columns,
                        True,
                        self.document_id,
                        self.snapshot_revision,
                        self.run_id,
                    )
                self._close()
                return result
            return None
        self._close()
        return result

    def stop(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._process.join(timeout=1)
        self._queue.close()
        self._closed = True


MAX_MESSAGE_BYTES = 1_000_000
MAX_SNAPSHOT_CELLS = 100_000
MAX_CELL_BYTES = 64_000
MAX_DISPLAY_RESULTS = 8
MAX_PREVIEW_ROWS = 100
MAX_PREVIEW_COLUMNS = 30
MAX_VARIABLES = 200


class SessionState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    IDLE = "idle"
    RUNNING = "running"
    INTERRUPTING = "interrupting"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SessionCommand:
    source: str
    source_id: str
    source_version: int
    document_id: str
    snapshot_revision: int
    run_id: str
    session_id: str
    cells: dict[tuple[int, int], str]
    rows: int
    columns: int
    interactive: bool = False
    script_path: str | None = None


@dataclass(frozen=True, slots=True)
class SessionResult:
    output: str
    changes: dict[tuple[int, int], str]
    rows: int
    columns: int
    failed: bool
    document_id: str
    snapshot_revision: int
    run_id: str
    session_id: str
    source_id: str
    source_version: int
    interrupted: bool = False
    stdout: str = ""
    stderr: str = ""
    exception: ExceptionInfo | None = None
    displays: tuple[DisplayResult, ...] = ()
    duration_ms: int = 0


class _BoundedStream(StringIO):
    def __init__(self, emit: Callable[[str], None] | None = None) -> None:
        super().__init__()
        self.truncated = False
        self._emit = emit

    def write(self, value: str) -> int:
        if not isinstance(value, str):
            raise TypeError("output must be text")
        remaining = MAX_MESSAGE_BYTES - self.tell()
        if remaining > 0:
            super().write(value[:remaining])
        if len(value) > remaining:
            self.truncated = True
        if self._emit is not None and remaining > 0:
            self._emit(value[:remaining])
        return len(value)

    def output(self) -> str:
        value = self.getvalue()
        return value + ("\n[Output truncated.]\n" if self.truncated else "")


def _unsupported_input(*_: object, **__: object) -> str:
    raise RuntimeError("input() is not supported in Sheet Python sessions")


def _safe_text(value: object, *, limit: int = 240) -> str:
    """Format supported scalar values without invoking arbitrary representations."""
    if value is None:
        text = "None"
    elif type(value) is str:
        text = value
    elif type(value) is bytes:
        text = value.decode("utf-8", "replace")
    elif type(value) in {bool, int, float, complex}:
        text = str(value)
    elif isinstance(value, date | datetime):
        text = value.isoformat()
    else:
        text = f"<{type(value).__name__}>"
    return text if len(text) <= limit else f"{text[:limit]}..."


def _table_preview(frame, *, start: int = 0, rows: int = MAX_PREVIEW_ROWS) -> VariablePage:
    total_rows, total_columns = frame.shape
    column_count = min(total_columns, MAX_PREVIEW_COLUMNS)
    row_count = min(max(0, rows), MAX_PREVIEW_ROWS, max(0, total_rows - start))
    preview = frame.iloc[start : start + row_count, :column_count]
    columns = tuple(_safe_text(value) for value in preview.columns.tolist())
    index = tuple(_safe_text(value) for value in preview.index.tolist())
    raw_rows = tuple(preview.itertuples(index=False, name=None))
    values = tuple(tuple(_safe_text(value) for value in row) for row in raw_rows)
    write_error = ""
    sheet_rows: list[tuple[str, ...]] = []
    for row in raw_rows:
        try:
            sheet_rows.append(tuple(_cell_input(value) for value in row))
        except TypeError:
            write_error = "This page has values unsupported by the sheet API."
            sheet_rows = []
            break
    missing = tuple(int(value) for value in preview.isna().sum().tolist())
    return VariablePage(
        "",
        columns,
        tuple(_safe_text(value) for value in preview.dtypes.tolist()),
        index,
        values,
        total_rows,
        total_columns,
        start + row_count < total_rows or column_count < total_columns,
        missing,
        start,
        tuple(sheet_rows),
        write_error,
    )


def _display_value(value: object, displays: list[DisplayResult]) -> None:
    if len(displays) >= MAX_DISPLAY_RESULTS:
        return
    import pandas as pd
    import plotly.graph_objects as go

    if isinstance(value, (pd.DataFrame, pd.Series)):
        frame = value.to_frame() if isinstance(value, pd.Series) else value
        page = _table_preview(frame)
        displays.append(
            DisplayResult(
                "table",
                f"DataFrame {page.total_rows} x {page.total_columns}",
                page.columns,
                page.index,
                page.rows,
                page.partial,
            )
        )
    elif isinstance(value, go.Figure):
        value.show()
        displays.append(DisplayResult("plotly", "Opened Plotly figure in the browser."))
    else:
        displays.append(DisplayResult("text", _safe_text(value)))


def _exception_info(error: BaseException, command: SessionCommand) -> ExceptionInfo:
    filename = command.script_path or f"<sheet-{command.source_id}>"
    frames = tuple(
        ExceptionFrame(
            frame.filename,
            frame.lineno or 0,
            frame.name,
            command.source_id if frame.filename == filename else "",
            command.source_version if frame.filename == filename else 0,
        )
        for frame in traceback.extract_tb(error.__traceback__)
    )
    return ExceptionInfo(type(error).__name__, _safe_text(str(error), limit=500), frames)


def _variable_snapshot(
    namespace: dict[str, object], handles: dict[str, object]
) -> tuple[VariableInfo, ...]:
    import pandas as pd

    handles.clear()
    variables: list[VariableInfo] = []
    ignored = {"sheet", "pd", "px", "display", "input"}
    for name in sorted(namespace):
        if name.startswith("_") or name in ignored or len(variables) >= MAX_VARIABLES:
            continue
        value = namespace[name]
        type_name = type(value).__name__
        rows = columns = 0
        if isinstance(value, pd.DataFrame):
            rows, columns = value.shape
            summary = f"DataFrame {rows} x {columns}"
        elif isinstance(value, pd.Series):
            rows, columns = len(value), 1
            summary = f"Series {rows}"
        elif type(value) in {list, tuple, dict, set, frozenset}:
            summary = f"{type_name} ({len(value if isinstance(value, Sized) else ())})"
        elif type(value) in {str, bytes}:
            summary = _safe_text(value)
            rows = len(value if isinstance(value, Sized) else ())
        else:
            summary = _safe_text(value)
        handle = uuid.uuid4().hex
        handles[handle] = value
        variables.append(VariableInfo(name, type_name, summary, handle, rows, columns))
    return tuple(variables)


def _variable_page(handles: dict[str, object], handle: object, start: object) -> VariablePage:
    import pandas as pd

    if not isinstance(handle, str) or type(start) is not int or start < 0:
        raise ValueError("invalid variable handle")
    value = handles.get(handle)
    if isinstance(value, pd.Series):
        value = value.to_frame()
    if not isinstance(value, pd.DataFrame):
        raise ValueError("variable is no longer a DataFrame or Series")
    page = _table_preview(value, start=start)
    return VariablePage(
        handle,
        page.columns,
        page.dtypes,
        page.index,
        page.rows,
        page.total_rows,
        page.total_columns,
        page.partial,
        page.missing,
        page.start,
        page.sheet_rows,
        page.write_error,
    )


def _inspection_payload(inspection: SessionInspection) -> dict[str, object]:
    page = inspection.page
    return {
        "kind": "inspection",
        "request_id": inspection.request_id,
        "session_id": inspection.session_id,
        "variables": [
            {
                "name": variable.name,
                "type_name": variable.type_name,
                "summary": variable.summary,
                "handle": variable.handle,
                "rows": variable.rows,
                "columns": variable.columns,
            }
            for variable in inspection.variables
        ],
        "page": None
        if page is None
        else {
            "handle": page.handle,
            "columns": list(page.columns),
            "dtypes": list(page.dtypes),
            "index": list(page.index),
            "rows": [list(row) for row in page.rows],
            "total_rows": page.total_rows,
            "total_columns": page.total_columns,
            "partial": page.partial,
            "missing": list(page.missing),
            "start": page.start,
            "sheet_rows": [list(row) for row in page.sheet_rows],
            "write_error": page.write_error,
        },
        "error": inspection.error,
    }


def _inspection_from_payload(payload: object, session_id: str) -> SessionInspection:
    if not isinstance(payload, dict) or payload.get("kind") != "inspection":
        raise ValueError("invalid inspection")
    if payload.get("session_id") != session_id:
        raise ValueError("inspection session mismatch")
    variables_value = payload.get("variables")
    if not isinstance(variables_value, list) or len(variables_value) > MAX_VARIABLES:
        raise ValueError("invalid variables")
    variables: list[VariableInfo] = []
    for value in variables_value:
        if (
            not isinstance(value, dict)
            or type(value.get("rows")) is not int
            or type(value.get("columns")) is not int
        ):
            raise ValueError("invalid variable")
        variables.append(
            VariableInfo(
                _validate_text(value.get("name"), "variable name", limit=256),
                _validate_text(value.get("type_name"), "variable type", limit=256),
                _validate_text(value.get("summary"), "variable summary", limit=1024),
                _validate_text(value.get("handle"), "variable handle", limit=256),
                value["rows"],
                value["columns"],
            )
        )
    page_value = payload.get("page")
    page: VariablePage | None = None
    if page_value is not None:
        if not isinstance(page_value, dict) or not isinstance(page_value.get("partial"), bool):
            raise ValueError("invalid variable page")
        columns = page_value.get("columns")
        dtypes = page_value.get("dtypes")
        index = page_value.get("index")
        rows = page_value.get("rows")
        missing = page_value.get("missing")
        sheet_rows = page_value.get("sheet_rows")
        if (
            not isinstance(columns, list)
            or not isinstance(dtypes, list)
            or not isinstance(index, list)
            or not isinstance(rows, list)
            or not isinstance(missing, list)
            or not isinstance(sheet_rows, list)
        ):
            raise ValueError("invalid variable page values")
        if (
            len(columns) > MAX_PREVIEW_COLUMNS
            or len(index) > MAX_PREVIEW_ROWS
            or len(rows) > MAX_PREVIEW_ROWS
        ):
            raise ValueError("variable page exceeds preview limits")
        page = VariablePage(
            _validate_text(page_value.get("handle"), "variable handle", limit=256),
            tuple(_validate_text(value, "column", limit=1024) for value in columns),
            tuple(_validate_text(value, "dtype", limit=1024) for value in dtypes),
            tuple(_validate_text(value, "index", limit=1024) for value in index),
            tuple(
                tuple(_validate_text(cell, "table cell", limit=4096) for cell in row)
                for row in rows
                if isinstance(row, list)
            ),
            page_value.get("total_rows", 0),
            page_value.get("total_columns", 0),
            page_value["partial"],
            tuple(value for value in missing if type(value) is int),
            page_value.get("start", 0),
            tuple(
                tuple(_validate_text(cell, "sheet cell", limit=4096) for cell in row)
                for row in sheet_rows
                if isinstance(row, list)
            ),
            _validate_text(page_value.get("write_error"), "write error", limit=1024),
        )
    return SessionInspection(
        _validate_text(payload.get("request_id"), "request identity", limit=256),
        session_id,
        tuple(variables),
        page,
        _validate_text(payload.get("error"), "inspection error", limit=1024),
    )


def _validate_text(value: object, name: str, *, limit: int = MAX_MESSAGE_BYTES) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{name} exceeds the {limit}-byte limit")
    return value


def _validate_cells(value: object, rows: int, columns: int) -> dict[tuple[int, int], str]:
    if not isinstance(value, dict) or len(value) > MAX_SNAPSHOT_CELLS:
        raise ValueError("snapshot contains too many cells")
    cells: dict[tuple[int, int], str] = {}
    size = 0
    for coordinate, raw in value.items():
        if (
            not isinstance(coordinate, tuple)
            or len(coordinate) != 2
            or type(coordinate[0]) is not int
            or type(coordinate[1]) is not int
            or not 0 <= coordinate[0] < rows
            or not 0 <= coordinate[1] < columns
        ):
            raise ValueError("snapshot has an invalid cell coordinate")
        raw_value = _validate_text(raw, "cell value", limit=MAX_CELL_BYTES)
        size += len(raw_value.encode("utf-8"))
        if size > MAX_MESSAGE_BYTES:
            raise ValueError("snapshot exceeds the message-size limit")
        cells[coordinate] = raw_value
    return cells


def _validate_payload_size(text: str, cells: dict[tuple[int, int], str]) -> None:
    size = len(text.encode("utf-8")) + sum(len(raw.encode("utf-8")) for raw in cells.values())
    if size > MAX_MESSAGE_BYTES:
        raise ValueError(f"message exceeds the {MAX_MESSAGE_BYTES}-byte limit")


def _cells_payload(cells: Mapping[tuple[int, int], str]) -> list[list[object]]:
    """Encode cell dictionaries as JSON-safe [row, column, value] triples."""
    return [[row, column, value] for (row, column), value in cells.items()]


def _cells_from_payload(value: object, rows: int, columns: int) -> dict[tuple[int, int], str]:
    if not isinstance(value, list) or len(value) > MAX_SNAPSHOT_CELLS:
        raise ValueError("snapshot contains too many cells")
    entries: dict[tuple[int, int], str] = {}
    for item in value:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError("snapshot has an invalid cell coordinate")
        entries[(item[0], item[1])] = item[2]
    return _validate_cells(entries, rows, columns)


def _command_payload(command: SessionCommand) -> dict[str, object]:
    return {
        "kind": "execute",
        "source": command.source,
        "source_id": command.source_id,
        "source_version": command.source_version,
        "document_id": command.document_id,
        "snapshot_revision": command.snapshot_revision,
        "run_id": command.run_id,
        "session_id": command.session_id,
        "cells": _cells_payload(command.cells),
        "rows": command.rows,
        "columns": command.columns,
        "interactive": command.interactive,
        "script_path": command.script_path,
    }


def _command_from_payload(payload: object, session_id: str) -> SessionCommand:
    if not isinstance(payload, dict) or payload.get("kind") != "execute":
        raise ValueError("unsupported session command")
    rows = payload.get("rows")
    columns = payload.get("columns")
    source_version = payload.get("source_version")
    snapshot_revision = payload.get("snapshot_revision")
    if (
        type(rows) is not int
        or type(columns) is not int
        or rows < 1
        or columns < 1
        or type(source_version) is not int
        or type(snapshot_revision) is not int
        or payload.get("session_id") != session_id
        or not isinstance(payload.get("interactive"), bool)
    ):
        raise ValueError("invalid session command metadata")
    script_path = payload.get("script_path")
    if script_path is not None:
        script_path = _validate_text(script_path, "script path")
    source = _validate_text(payload.get("source"), "source")
    cells = _cells_from_payload(payload.get("cells"), rows, columns)
    _validate_payload_size(source, cells)
    return SessionCommand(
        source,
        _validate_text(payload.get("source_id"), "source identity", limit=256),
        source_version,
        _validate_text(payload.get("document_id"), "document identity", limit=256),
        snapshot_revision,
        _validate_text(payload.get("run_id"), "run identity", limit=256),
        session_id,
        cells,
        rows,
        columns,
        payload["interactive"],
        script_path,
    )


def _result_payload(result: SessionResult) -> dict[str, object]:
    return {
        "kind": "result",
        "output": result.output,
        "changes": _cells_payload(result.changes),
        "rows": result.rows,
        "columns": result.columns,
        "failed": result.failed,
        "document_id": result.document_id,
        "snapshot_revision": result.snapshot_revision,
        "run_id": result.run_id,
        "session_id": result.session_id,
        "source_id": result.source_id,
        "source_version": result.source_version,
        "interrupted": result.interrupted,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exception": _exception_payload(result.exception),
        "displays": [_display_payload(display) for display in result.displays],
        "duration_ms": result.duration_ms,
    }


def _exception_payload(exception: ExceptionInfo | None) -> dict[str, object] | None:
    if exception is None:
        return None
    return {
        "type_name": exception.type_name,
        "message": exception.message,
        "frames": [
            {
                "filename": frame.filename,
                "line": frame.line,
                "function": frame.function,
                "source_id": frame.source_id,
                "source_version": frame.source_version,
            }
            for frame in exception.frames
        ],
    }


def _exception_from_payload(value: object) -> ExceptionInfo | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid exception")
    frames: list[ExceptionFrame] = []
    raw_frames = value.get("frames")
    if not isinstance(raw_frames, list):
        raise ValueError("invalid exception frames")
    for frame in raw_frames[:100]:
        if (
            not isinstance(frame, dict)
            or type(frame.get("line")) is not int
            or type(frame.get("source_version")) is not int
        ):
            raise ValueError("invalid exception frame")
        frames.append(
            ExceptionFrame(
                _validate_text(frame.get("filename"), "exception filename", limit=1024),
                frame["line"],
                _validate_text(frame.get("function"), "exception function", limit=256),
                _validate_text(frame.get("source_id"), "source identity", limit=256),
                frame["source_version"],
            )
        )
    return ExceptionInfo(
        _validate_text(value.get("type_name"), "exception type", limit=256),
        _validate_text(value.get("message"), "exception message", limit=2048),
        tuple(frames),
    )


def _display_payload(display: DisplayResult) -> dict[str, object]:
    return {
        "kind": display.kind,
        "text": display.text,
        "columns": list(display.columns),
        "index": list(display.index),
        "rows": [list(row) for row in display.rows],
        "partial": display.partial,
    }


def _displays_from_payload(value: object) -> tuple[DisplayResult, ...]:
    if not isinstance(value, list) or len(value) > MAX_DISPLAY_RESULTS:
        raise ValueError("invalid display results")
    displays: list[DisplayResult] = []
    for display in value:
        if not isinstance(display, dict) or not isinstance(display.get("partial"), bool):
            raise ValueError("invalid display result")
        columns = display.get("columns")
        index = display.get("index")
        rows = display.get("rows")
        if (
            not isinstance(columns, list)
            or not isinstance(index, list)
            or not isinstance(rows, list)
        ):
            raise ValueError("invalid display table")
        if len(columns) > MAX_PREVIEW_COLUMNS or len(index) > MAX_PREVIEW_ROWS:
            raise ValueError("display table exceeds preview limits")
        parsed_rows: list[tuple[str, ...]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) > MAX_PREVIEW_COLUMNS:
                raise ValueError("invalid display row")
            parsed_rows.append(
                tuple(_validate_text(cell, "display cell", limit=4096) for cell in row)
            )
        displays.append(
            DisplayResult(
                _validate_text(display.get("kind"), "display kind", limit=32),
                _validate_text(display.get("text"), "display text", limit=4096),
                tuple(_validate_text(cell, "display column", limit=1024) for cell in columns),
                tuple(_validate_text(cell, "display index", limit=1024) for cell in index),
                tuple(parsed_rows),
                display["partial"],
            )
        )
    return tuple(displays)


def _output_from_payload(payload: dict[str, object], session_id: str) -> OutputEvent | None:
    if payload.get("session_id") != session_id:
        return None
    sequence = payload.get("sequence")
    channel = payload.get("channel")
    if (
        type(sequence) is not int
        or not isinstance(channel, str)
        or channel not in {"stdout", "stderr"}
    ):
        return None
    try:
        return OutputEvent(
            _validate_text(payload.get("run_id"), "run identity", limit=256),
            channel,
            sequence,
            _validate_text(payload.get("text"), "output", limit=MAX_MESSAGE_BYTES),
        )
    except ValueError:
        return None


def _result_from_payload(payload: object, session_id: str) -> SessionResult:
    if not isinstance(payload, dict) or payload.get("kind") != "result":
        raise ValueError("invalid session response")
    rows = payload.get("rows")
    columns = payload.get("columns")
    source_version = payload.get("source_version")
    snapshot_revision = payload.get("snapshot_revision")
    failed = payload.get("failed")
    interrupted = payload.get("interrupted")
    duration_ms = payload.get("duration_ms")
    if (
        type(rows) is not int
        or type(columns) is not int
        or rows < 1
        or columns < 1
        or type(source_version) is not int
        or type(snapshot_revision) is not int
        or not isinstance(failed, bool)
        or not isinstance(interrupted, bool)
        or type(duration_ms) is not int
        or duration_ms < 0
        or payload.get("session_id") != session_id
    ):
        raise ValueError("invalid session response metadata")
    output = _validate_text(payload.get("output"), "output")
    stdout = _validate_text(payload.get("stdout"), "stdout")
    stderr = _validate_text(payload.get("stderr"), "stderr")
    changes = _cells_from_payload(payload.get("changes"), rows, columns)
    _validate_payload_size(output, changes)
    return SessionResult(
        output,
        changes,
        rows,
        columns,
        failed,
        _validate_text(payload.get("document_id"), "document identity", limit=256),
        snapshot_revision,
        _validate_text(payload.get("run_id"), "run identity", limit=256),
        session_id,
        _validate_text(payload.get("source_id"), "source identity", limit=256),
        source_version,
        interrupted,
        stdout,
        stderr,
        _exception_from_payload(payload.get("exception")),
        _displays_from_payload(payload.get("displays")),
        duration_ms,
    )


def _execute_session_source(
    command: SessionCommand,
    namespace: dict[str, object],
    stdout: _BoundedStream,
    stderr: _BoundedStream,
    interrupt_event: Event,
) -> tuple[bool, bool, ExceptionInfo | None, tuple[DisplayResult, ...]]:
    failed = False
    interrupted = False
    exception: ExceptionInfo | None = None
    displays: list[DisplayResult] = []
    filename = command.script_path or f"<sheet-{command.source_id}>"
    path_inserted = False
    previous_file = namespace.get("__file__")
    if command.script_path is not None:
        sys.path.insert(0, str(Path(command.script_path).parent))
        namespace["__file__"] = command.script_path
        path_inserted = True
    else:
        namespace.pop("__file__", None)
    namespace["display"] = lambda value: _display_value(value, displays)

    def interrupt_trace(*_: object):
        if interrupt_event.is_set():
            raise KeyboardInterrupt("session interrupted")
        return interrupt_trace

    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                tree = ast.parse(command.source, filename, "exec")
                previous_trace = sys.gettrace()
                sys.settrace(interrupt_trace)
                try:
                    if command.interactive and tree.body and isinstance(tree.body[-1], ast.Expr):
                        statements = ast.Module(tree.body[:-1], [])
                        if statements.body:
                            exec(compile(statements, filename, "exec"), namespace)
                        expression = compile(ast.Expression(tree.body[-1].value), filename, "eval")
                        value = eval(expression, namespace)
                        if value is not None:
                            sys.displayhook(value)
                    else:
                        exec(compile(tree, filename, "exec"), namespace)
                finally:
                    sys.settrace(previous_trace)
            except BaseException as error:
                failed = True
                interrupted = isinstance(error, KeyboardInterrupt)
                exception = _exception_info(error, command)
                traceback.print_exc()
    finally:
        if path_inserted:
            sys.path.pop(0)
        if previous_file is None:
            namespace.pop("__file__", None)
        else:
            namespace["__file__"] = previous_file
    return failed, interrupted, exception, tuple(displays)


def _session_worker(
    command_queue: Queue[dict[str, object]],
    result_queue: Queue[dict[str, object]],
    interrupt_event: Event,
    session_id: str,
) -> None:
    _run_session_loop(command_queue.get, result_queue.put, interrupt_event, session_id)


def _run_session_loop(
    get_command: Callable[[], object],
    send_message: Callable[[dict[str, object]], None],
    interrupt_flag: Any,
    session_id: str,
) -> None:
    """Serve one session over any message transport.

    ``get_command`` blocks until the next command payload (any object); ``send_message``
    delivers worker messages (ready/output/inspection/result). ``interrupt_flag`` needs
    ``is_set()``/``clear()`` and is polled through a trace function while user code runs.
    """
    import pandas as pd
    import plotly.express as px

    namespace: dict[str, object] = {
        "__builtins__": builtins.__dict__,
        "__name__": "__sheet_session__",
        "pd": pd,
        "px": px,
        "input": _unsupported_input,
    }
    send_message({"kind": "ready", "session_id": session_id})
    sheet: SheetAPI | None = None
    variable_handles: dict[str, object] = {}
    while True:
        payload = get_command()
        if isinstance(payload, dict) and payload.get("kind") == "shutdown":
            return
        if isinstance(payload, dict) and payload.get("kind") in {"variables", "variable_page"}:
            request_id = payload.get("request_id")
            if not isinstance(request_id, str) or payload.get("session_id") != session_id:
                continue
            try:
                inspection = (
                    SessionInspection(
                        request_id, session_id, _variable_snapshot(namespace, variable_handles)
                    )
                    if payload["kind"] == "variables"
                    else SessionInspection(
                        request_id,
                        session_id,
                        page=_variable_page(
                            variable_handles, payload.get("handle"), payload.get("start")
                        ),
                    )
                )
            except (TypeError, ValueError) as error:
                inspection = SessionInspection(request_id, session_id, error=str(error))
            send_message(_inspection_payload(inspection))
            continue
        try:
            command = _command_from_payload(payload, session_id)
        except ValueError:
            continue
        workbook = Workbook(":memory:", recovery_enabled=False)
        variable_handles.clear()
        workbook.resize(command.rows, command.columns)
        workbook.set_cells(command.cells)
        original_cells = dict(workbook.cells)
        if sheet is None:
            sheet = SheetAPI(workbook)
            namespace["sheet"] = sheet
        else:
            sheet.rebind(workbook)
        sequence = 0

        def emit(channel: str, run_id: str = command.run_id) -> Callable[[str], None]:
            def send(text: str) -> None:
                nonlocal sequence
                sequence += 1
                send_message(
                    {
                        "kind": "output",
                        "session_id": session_id,
                        "run_id": run_id,
                        "channel": channel,
                        "sequence": sequence,
                        "text": text,
                    }
                )

            return send

        stdout = _BoundedStream(emit("stdout"))
        stderr = _BoundedStream(emit("stderr"))
        started = time.monotonic()

        try:
            failed, interrupted, exception, displays = _execute_session_source(
                command, namespace, stdout, stderr, interrupt_flag
            )
        finally:
            interrupt_flag.clear()
        changes: dict[tuple[int, int], str] = {}
        if not failed:
            changes = {
                coordinate: workbook.raw_value(*coordinate)
                for coordinate in set(original_cells) | set(workbook.cells)
                if original_cells.get(coordinate, "") != workbook.raw_value(*coordinate)
            }
        try:
            _validate_cells(changes, workbook.rows, workbook.columns)
        except ValueError as error:
            failed = True
            changes = {}
            stderr.write(f"\nSession result discarded: {error}\n")
        stdout_text = stdout.output()
        stderr_text = stderr.output()
        output = stdout_text + stderr_text
        if (
            len(output.encode("utf-8")) + sum(len(raw.encode("utf-8")) for raw in changes.values())
            > MAX_MESSAGE_BYTES
        ):
            available = MAX_MESSAGE_BYTES - sum(
                len(raw.encode("utf-8")) for raw in changes.values()
            )
            output = output.encode("utf-8")[: max(0, available)].decode("utf-8", "ignore")
        send_message(
            _result_payload(
                SessionResult(
                    output,
                    changes,
                    workbook.rows,
                    workbook.columns,
                    failed,
                    command.document_id,
                    command.snapshot_revision,
                    command.run_id,
                    command.session_id,
                    command.source_id,
                    command.source_version,
                    interrupted,
                    stdout_text,
                    stderr_text,
                    exception,
                    displays,
                    int((time.monotonic() - started) * 1000),
                )
            )
        )
        workbook.close()


class ScriptSession:
    """A spawned, serial Python namespace for one active workbook document."""

    def __init__(self, *, interrupt_grace: float = 1.0) -> None:
        if interrupt_grace <= 0:
            raise ValueError("interrupt_grace must be positive")
        self._context = multiprocessing.get_context("spawn")
        self._interrupt_grace = interrupt_grace
        self._command_queue: Queue[dict[str, object]] | None = None
        self._result_queue: Queue[dict[str, object]] | None = None
        self._interrupt_event: Event | None = None
        self._process: BaseProcess | None = None
        self._current: SessionCommand | None = None
        self._deadline: float | None = None
        self._deadline_reason = ""
        self._exit_reported = False
        self._output_events: list[OutputEvent] = []
        self._inspections: list[SessionInspection] = []
        self.session_id = ""
        self.state = SessionState.STOPPED

    @property
    def running(self) -> bool:
        return self.state in {SessionState.RUNNING, SessionState.INTERRUPTING}

    def start(self) -> None:
        if self.state in {
            SessionState.STARTING,
            SessionState.IDLE,
            SessionState.RUNNING,
            SessionState.INTERRUPTING,
        }:
            return
        self.session_id = uuid.uuid4().hex
        self._command_queue = self._context.Queue()
        self._result_queue = self._context.Queue()
        self._interrupt_event = self._context.Event()
        process = self._context.Process(
            target=_session_worker,
            args=(self._command_queue, self._result_queue, self._interrupt_event, self.session_id),
            daemon=True,
        )
        self._process = process
        process.start()
        self._current = None
        self._deadline = None
        self._exit_reported = False
        self._output_events.clear()
        self._inspections.clear()
        self.state = SessionState.STARTING

    def run(
        self,
        source: str,
        workbook: Workbook,
        *,
        source_id: str,
        source_version: int,
        interactive: bool = False,
        script_path: str | None = None,
        timeout: float | None = None,
    ) -> str:
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.state == SessionState.STOPPED or self.state == SessionState.FAILED:
            self.start()
        if (
            self.state not in {SessionState.STARTING, SessionState.IDLE}
            or self._command_queue is None
        ):
            raise RuntimeError("a session command is already running")
        validated_source = _validate_text(source, "source")
        cells = _validate_cells(dict(workbook.cells), workbook.rows, workbook.columns)
        _validate_payload_size(validated_source, cells)
        command = SessionCommand(
            validated_source,
            _validate_text(source_id, "source identity", limit=256),
            source_version,
            workbook.document_id,
            workbook.revision,
            uuid.uuid4().hex,
            self.session_id,
            cells,
            workbook.rows,
            workbook.columns,
            interactive,
            script_path,
        )
        self._command_queue.put(_command_payload(command))
        self._current = command
        self._deadline = time.monotonic() + timeout if timeout is not None else None
        self._deadline_reason = "timeout"
        self.state = SessionState.RUNNING
        return command.run_id

    execute = run

    def inspect_variables(self) -> str:
        return self._inspect("variables")

    def inspect_variable_page(self, handle: str, start: int = 0) -> str:
        return self._inspect("variable_page", handle=handle, start=start)

    def _inspect(self, kind: str, **payload: object) -> str:
        if self.state != SessionState.IDLE or self._command_queue is None:
            raise RuntimeError("the session must be idle to inspect variables")
        request_id = uuid.uuid4().hex
        self._command_queue.put(
            {"kind": kind, "request_id": request_id, "session_id": self.session_id, **payload}
        )
        return request_id

    def take_output_events(self) -> list[OutputEvent]:
        events = self._output_events
        self._output_events = []
        return events

    def take_inspections(self) -> list[SessionInspection]:
        inspections = self._inspections
        self._inspections = []
        return inspections

    def interrupt(self) -> bool:
        if self.state != SessionState.RUNNING or self._interrupt_event is None:
            return False
        self._interrupt_event.set()
        self._deadline = time.monotonic() + self._interrupt_grace
        self._deadline_reason = "interrupt"
        self.state = SessionState.INTERRUPTING
        return True

    def restart(self) -> None:
        self.stop()
        self.start()

    def stop(self) -> None:
        if (
            self._command_queue is not None
            and self._process is not None
            and self._process.is_alive()
        ):
            self._command_queue.put({"kind": "shutdown", "session_id": self.session_id})
            self._process.join(timeout=0.2)
        self._dispose_process()
        self._current = None
        self._deadline = None
        self.state = SessionState.STOPPED

    def poll(self) -> SessionResult | None:
        result_queue = self._result_queue
        completed: SessionResult | None = None
        if result_queue is not None:
            while True:
                try:
                    payload = result_queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(payload, dict) and payload.get("kind") == "ready":
                    if payload.get("session_id") == self.session_id and self._current is None:
                        self.state = SessionState.IDLE
                    continue
                if isinstance(payload, dict) and payload.get("kind") == "output":
                    event = _output_from_payload(payload, self.session_id)
                    if event is not None:
                        self._output_events.append(event)
                    continue
                if isinstance(payload, dict) and payload.get("kind") == "inspection":
                    with suppress(ValueError):
                        self._inspections.append(_inspection_from_payload(payload, self.session_id))
                    continue
                try:
                    result = _result_from_payload(payload, self.session_id)
                except ValueError:
                    continue
                if self._current is None or result.run_id != self._current.run_id:
                    continue
                self._current = None
                self._deadline = None
                self.state = SessionState.IDLE
                completed = result
                continue
        if completed is not None:
            return completed
        if self._deadline is not None and time.monotonic() >= self._deadline:
            return self._terminate_current(
                "Session timed out and was terminated; session variables were lost."
                if self._deadline_reason == "timeout"
                else (
                    "Session was terminated after the interrupt grace period; "
                    "session variables were lost."
                )
            )
        if self._process is not None and not self._process.is_alive() and not self._exit_reported:
            self._exit_reported = True
            command = self._current
            self._current = None
            self._deadline = None
            self.state = SessionState.FAILED
            self._dispose_process()
            return SessionResult(
                "Session process exited without returning a result.",
                {},
                command.rows if command else 1,
                command.columns if command else 1,
                True,
                command.document_id if command else "",
                command.snapshot_revision if command else 0,
                command.run_id if command else "",
                self.session_id,
                command.source_id if command else "",
                command.source_version if command else 0,
            )
        return None

    def _terminate_current(self, output: str) -> SessionResult | None:
        command = self._current
        if command is None:
            return None
        self._current = None
        self._deadline = None
        self.state = SessionState.FAILED
        self._dispose_process()
        return SessionResult(
            output,
            {},
            command.rows,
            command.columns,
            True,
            command.document_id,
            command.snapshot_revision,
            command.run_id,
            command.session_id,
            command.source_id,
            command.source_version,
            True,
        )

    def _dispose_process(self) -> None:
        if self._process is not None:
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=0.2)
        if self._command_queue is not None:
            self._command_queue.close()
        if self._result_queue is not None:
            self._result_queue.close()
        self._process = None
        self._command_queue = None
        self._result_queue = None
        self._interrupt_event = None


PythonSession = ScriptSession
