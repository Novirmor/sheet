import argparse
import multiprocessing
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from sheet import __version__
from sheet.theme import apply_theme
from sheet.window import MainWindow
from sheet.workbook import Workbook


def configure_display() -> None:
    if sys.platform != "linux" or "QT_QPA_PLATFORM" in os.environ:
        return
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text().lower()
    except OSError:
        return
    if "microsoft" not in release:
        return
    if os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    elif os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "wayland"


def present_window(window: MainWindow, *, center: bool = False) -> None:
    window.showNormal()
    if center:
        screen = QApplication.primaryScreen()
        if screen is not None:
            frame = window.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            window.move(frame.topLeft())
    window.raise_()
    window.activateWindow()
    QApplication.alert(window, 2000)


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A small SQLite-backed spreadsheet")
    parser.add_argument("--version", action="store_true", help="show the application version")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="run headless packaging checks and exit",
    )
    parser.add_argument(
        "--smoke-test-interpreter",
        type=Path,
        default=None,
        metavar="PATH",
        help="also probe this external Python interpreter during --smoke-test",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="spreadsheet database to open",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    options = parse_args(arguments)
    if options.version:
        if sys.stdout is not None:
            sys.stdout.write(f"Sheet {__version__}\n")
        return 0
    if options.smoke_test:
        from sheet.smoke_test import run_smoke_test

        return run_smoke_test(
            interpreter=options.smoke_test_interpreter,
            stream=sys.stdout if sys.stdout is not None else None,
        )
    configure_display()
    app = QApplication(sys.argv if arguments is None else [sys.argv[0], *arguments])
    app.setApplicationName("Sheet")
    app.setApplicationDisplayName("Sheet")
    app.setOrganizationName("Sheet")
    apply_theme(app)
    window = MainWindow(options.file or ":memory:")
    snapshots = Workbook.recovery_snapshots()
    if options.file is not None:
        snapshots = [snapshot for snapshot in snapshots if snapshot.source == options.file]
    for snapshot in snapshots:
        source_name = (
            snapshot.source.name if snapshot.source is not None else "an untitled spreadsheet"
        )
        answer = QMessageBox.question(
            window,
            "Recover spreadsheet?",
            f"Restore unsaved changes for {source_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Discard,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            window._replace_workbook(Workbook.from_recovery(snapshot))
            break
        Workbook.discard_recovery(snapshot)
    present_window(window, center=True)
    QTimer.singleShot(300, lambda: present_window(window, center=True))
    return app.exec()
