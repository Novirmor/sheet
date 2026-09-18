import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from sheet.database import SpreadsheetStore
from sheet.formatting import CellFormat

type CellCoordinate = tuple[int, int]


@dataclass(frozen=True, slots=True)
class RecoverySnapshot:
    path: Path
    source: Path | None


def user_recovery_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = (
        Path(local_app_data)
        if local_app_data
        else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    )
    return base / "Sheet" / "recovery"


def find_recovery_snapshots(directory: Path) -> list[RecoverySnapshot]:
    if not directory.exists():
        return []
    snapshots = [
        snapshot for path in directory.glob("*.sheet") if (snapshot := read_recovery(path))
    ]
    return sorted(snapshots, key=lambda snapshot: snapshot.path.stat().st_mtime, reverse=True)


def read_recovery(path: Path) -> RecoverySnapshot | None:
    try:
        store = SpreadsheetStore(path)
        try:
            source_value = store.metadata().get("recovery_source", "")
        finally:
            store.close()
        source = Path(source_value) if source_value else None
        if source is not None and source.exists() and source.stat().st_mtime > path.stat().st_mtime:
            return None
    except OSError, ValueError:
        return None
    return RecoverySnapshot(path, source)


def discard_snapshot(path: Path) -> None:
    for candidate in (path, path.with_suffix(".sheet-wal")):
        with suppress(FileNotFoundError):
            candidate.unlink()


def write_snapshot(
    destination: Path,
    *,
    rows: int,
    columns: int,
    cells: Mapping[CellCoordinate, str],
    formats: Mapping[CellCoordinate, CellFormat],
    scripts: Mapping[str, str],
    metadata: Mapping[str, str] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        _write_store(temporary_path, rows, columns, cells, formats, scripts, metadata)
        os.replace(temporary_path, destination)
    except BaseException:
        discard_snapshot(temporary_path)
        raise


def _write_store(
    path: Path,
    rows: int,
    columns: int,
    cells: Mapping[CellCoordinate, str],
    formats: Mapping[CellCoordinate, CellFormat],
    scripts: Mapping[str, str],
    metadata: Mapping[str, str] | None,
) -> None:
    store = SpreadsheetStore(path, journal_mode="DELETE")
    try:
        store.set_dimensions(rows, columns)
        store.replace_cells((row, column, value) for (row, column), value in cells.items())
        store.replace_formats((row, column, value) for (row, column), value in formats.items())
        store.replace_scripts(scripts.items())
        if metadata:
            store.set_metadata(dict(metadata))
    finally:
        store.close()
