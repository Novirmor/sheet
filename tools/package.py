import sys
from pathlib import Path

import PyInstaller.__main__
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen


def create_icon(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2563eb"))
    painter.drawRoundedRect(QRectF(12, 12, 232, 232), 42, 42)

    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(49, 48, 158, 160), 12, 12)
    painter.setBrush(QColor("#bfdbfe"))
    painter.drawRoundedRect(QRectF(49, 48, 158, 39), 12, 12)
    painter.drawRect(QRectF(49, 72, 158, 15))

    painter.setPen(QPen(QColor("#93c5fd"), 7))
    for position in (101, 154):
        painter.drawLine(position, 85, position, 208)
    for position in (127, 168):
        painter.drawLine(49, position, 207, position)
    painter.end()

    if not image.save(str(path)):
        raise RuntimeError(f"could not create application icon at {path}")


def main() -> int:
    arguments = [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "Sheet",
        "--paths",
        "src",
        "--hidden-import",
        "pandas",
        "--hidden-import",
        "plotly.express",
        "--collect-data",
        "plotly",
    ]
    if sys.platform == "win32":
        icon = Path("build/package/sheet.ico")
        create_icon(icon)
        arguments.extend(
            [
                "--icon",
                str(icon),
                "--version-file",
                "packaging/windows-version.txt",
            ]
        )
    arguments.append("src/sheet/__main__.py")
    PyInstaller.__main__.run(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
