from pathlib import Path

from sheet.csv_io import read_csv, write_csv


def test_csv_round_trip_preserves_quoted_and_multiline_values(tmp_path: Path) -> None:
    path = tmp_path / "report.csv"
    rows = [["Name", "Note"], ["Coffee, tea", 'He said "hello"\nand left']]

    write_csv(path, rows)

    assert read_csv(path) == rows


def test_csv_reader_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_bytes("\ufeffName,Amount\nCoffee,4.5\n".encode())

    assert read_csv(path) == [["Name", "Amount"], ["Coffee", "4.5"]]
