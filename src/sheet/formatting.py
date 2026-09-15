from dataclasses import dataclass

from sheet.formulas import CellValue, format_value

ALIGNMENTS = {"general", "left", "center", "right"}
NUMBER_FORMATS = {"general", "number", "currency", "percent"}


@dataclass(frozen=True, slots=True)
class CellFormat:
    bold: bool = False
    italic: bool = False
    alignment: str = "general"
    number_format: str = "general"

    @property
    def is_default(self) -> bool:
        return self == CellFormat()


def display_value(value: CellValue, number_format: str) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return format_value(value)
    if number_format == "number":
        return f"{value:,.2f}"
    if number_format == "currency":
        return f"${value:,.2f}"
    if number_format == "percent":
        return f"{value:.2%}"
    return format_value(value)
