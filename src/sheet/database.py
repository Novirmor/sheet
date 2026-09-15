import sqlite3
from collections.abc import Iterable
from pathlib import Path

from sheet.formatting import CellFormat


class SpreadsheetStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path) if path != ":memory:" else None
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cells (
                    row_index INTEGER NOT NULL CHECK (row_index >= 0),
                    column_index INTEGER NOT NULL CHECK (column_index >= 0),
                    input TEXT NOT NULL,
                    PRIMARY KEY (row_index, column_index)
                );

                CREATE TABLE IF NOT EXISTS cell_formats (
                    row_index INTEGER NOT NULL CHECK (row_index >= 0),
                    column_index INTEGER NOT NULL CHECK (column_index >= 0),
                    bold INTEGER NOT NULL DEFAULT 0,
                    italic INTEGER NOT NULL DEFAULT 0,
                    alignment TEXT NOT NULL DEFAULT 'general',
                    number_format TEXT NOT NULL DEFAULT 'general',
                    PRIMARY KEY (row_index, column_index)
                );
                """
            )

    def close(self) -> None:
        self._connection.close()

    def load_cells(self) -> dict[tuple[int, int], str]:
        rows = self._connection.execute(
            "SELECT row_index, column_index, input FROM cells"
        ).fetchall()
        return {(row, column): value for row, column, value in rows}

    def set_cell(self, row: int, column: int, value: str) -> None:
        self.set_cells(((row, column, value),))

    def set_cells(self, cells: Iterable[tuple[int, int, str]]) -> None:
        with self._connection:
            for row, column, value in cells:
                if value:
                    self._connection.execute(
                        """
                        INSERT INTO cells (row_index, column_index, input)
                        VALUES (?, ?, ?)
                        ON CONFLICT (row_index, column_index)
                        DO UPDATE SET input = excluded.input
                        """,
                        (row, column, value),
                    )
                else:
                    self._connection.execute(
                        "DELETE FROM cells WHERE row_index = ? AND column_index = ?",
                        (row, column),
                    )

    def load_formats(self) -> dict[tuple[int, int], CellFormat]:
        rows = self._connection.execute(
            """
            SELECT row_index, column_index, bold, italic, alignment, number_format
            FROM cell_formats
            """
        ).fetchall()
        return {
            (row, column): CellFormat(bool(bold), bool(italic), alignment, number_format)
            for row, column, bold, italic, alignment, number_format in rows
        }

    def set_format(self, row: int, column: int, cell_format: CellFormat) -> None:
        with self._connection:
            if cell_format.is_default:
                self._connection.execute(
                    "DELETE FROM cell_formats WHERE row_index = ? AND column_index = ?",
                    (row, column),
                )
            else:
                self._connection.execute(
                    """
                    INSERT INTO cell_formats (
                        row_index, column_index, bold, italic, alignment, number_format
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (row_index, column_index) DO UPDATE SET
                        bold = excluded.bold,
                        italic = excluded.italic,
                        alignment = excluded.alignment,
                        number_format = excluded.number_format
                    """,
                    (
                        row,
                        column,
                        cell_format.bold,
                        cell_format.italic,
                        cell_format.alignment,
                        cell_format.number_format,
                    ),
                )

    def dimensions(self, default_rows: int = 100, default_columns: int = 26) -> tuple[int, int]:
        values = dict(self._connection.execute("SELECT key, value FROM metadata"))
        rows = int(values.get("rows", default_rows))
        columns = int(values.get("columns", default_columns))
        return rows, columns

    def set_dimensions(self, rows: int, columns: int) -> None:
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT (key) DO UPDATE SET value = excluded.value
                """,
                (("rows", str(rows)), ("columns", str(columns))),
            )

    def replace_cells(self, cells: Iterable[tuple[int, int, str]]) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM cells")
            self._connection.executemany(
                "INSERT INTO cells (row_index, column_index, input) VALUES (?, ?, ?)",
                cells,
            )

    def replace_formats(self, formats: Iterable[tuple[int, int, CellFormat]]) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM cell_formats")
            self._connection.executemany(
                """
                INSERT INTO cell_formats (
                    row_index, column_index, bold, italic, alignment, number_format
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (row, column, value.bold, value.italic, value.alignment, value.number_format)
                    for row, column, value in formats
                ),
            )
