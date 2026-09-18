from pathlib import Path

import pytest

from sheet.csv_io import CsvCancelled, CsvError, read_csv, write_csv


def test_csv_round_trip_preserves_quoted_and_multiline_values(tmp_path: Path) -> None:
    path = tmp_path / "report.csv"
    rows = [["Name", "Note"], ["Coffee, tea", 'He said "hello"\nand left']]

    write_csv(path, rows)

    data = read_csv(path)
    assert data.rows == rows
    assert data.delimiter == ","


def test_csv_reader_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_bytes("\ufeffName,Amount\nCoffee,4.5\n".encode())

    assert read_csv(path).rows == [["Name", "Amount"], ["Coffee", "4.5"]]


def test_csv_reader_reports_inconsistent_rows(tmp_path: Path) -> None:
    path = tmp_path / "broken.csv"
    path.write_text("Name,Amount\nCoffee,4.5,extra\n")

    with pytest.raises(CsvError, match="row 2 has 3 columns; expected 2"):
        read_csv(path)


def test_csv_reader_and_writer_support_cancellation(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("\n".join("value" for _ in range(101)))

    with pytest.raises(CsvCancelled):
        read_csv(source, progress=lambda _: False)
    with pytest.raises(CsvCancelled):
        write_csv(
            tmp_path / "output.csv", (["value"] for _ in range(101)), progress=lambda _: False
        )
