from collections.abc import Iterable
from dataclasses import dataclass

type CellCoordinate = tuple[int, int]


@dataclass(frozen=True, slots=True)
class CellRange:
    top: int
    bottom: int
    left: int
    right: int


def bounds(coordinates: Iterable[CellCoordinate]) -> CellRange | None:
    selected = tuple(coordinates)
    if not selected:
        return None
    return CellRange(
        min(row for row, _ in selected),
        max(row for row, _ in selected),
        min(column for _, column in selected),
        max(column for _, column in selected),
    )


def contiguous_sections(sections: Iterable[int]) -> list[int]:
    selected = sorted(set(sections))
    return list(range(selected[0], selected[-1] + 1)) if selected else []
