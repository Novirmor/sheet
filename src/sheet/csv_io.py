import csv
from collections.abc import Iterable
from pathlib import Path


def read_csv(path: str | Path) -> list[list[str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.reader(file))


def write_csv(path: str | Path, rows: Iterable[Iterable[str]]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerows(rows)
