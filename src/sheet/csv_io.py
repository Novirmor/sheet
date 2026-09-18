import csv
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

type ProgressCallback = Callable[[int], bool]


class CsvError(ValueError):
    pass


class CsvCancelled(CsvError):
    pass


@dataclass(frozen=True, slots=True)
class CsvData:
    rows: list[list[str]]
    delimiter: str
    encoding: str

    @property
    def columns(self) -> int:
        return len(self.rows[0]) if self.rows else 0


def read_csv(path: str | Path, progress: ProgressCallback | None = None) -> CsvData:
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            sample = file.read(8192)
            file.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(file, dialect, strict=True)
            rows: list[list[str]] = []
            columns: int | None = None
            for row_number, row in enumerate(reader, start=1):
                if columns is None:
                    columns = len(row)
                elif len(row) != columns:
                    raise CsvError(f"row {row_number} has {len(row)} columns; expected {columns}")
                rows.append(row)
                if row_number % 100 == 0 and progress is not None and not progress(row_number):
                    raise CsvCancelled("CSV import cancelled")
    except UnicodeDecodeError as error:
        raise CsvError("CSV files must be UTF-8 encoded") from error
    except csv.Error as error:
        raise CsvError(f"malformed CSV: {error}") from error
    return CsvData(rows, dialect.delimiter, "utf-8")


def write_csv(
    path: str | Path, rows: Iterable[Iterable[str]], progress: ProgressCallback | None = None
) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        for row_number, row in enumerate(rows, start=1):
            writer.writerow(row)
            if row_number % 100 == 0 and progress is not None and not progress(row_number):
                raise CsvCancelled("CSV export cancelled")
