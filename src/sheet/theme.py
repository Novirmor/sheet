import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

STYLESHEET = """
QWidget {
    color: #182230;
}
QMainWindow#mainWindow {
    background: #f6f8fb;
}
QMenuBar {
    background: #ffffff;
    color: #182230;
    border-bottom: 1px solid #dfe3e8;
    padding: 4px 8px;
}
QMenuBar::item {
    background: transparent;
    color: #182230;
    border-radius: 4px;
    padding: 5px 10px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #eaf2ff;
    color: #1557b0;
}
QMenu {
    background: #ffffff;
    color: #182230;
    border: 1px solid #d7dce2;
    padding: 5px;
}
QMenu::item {
    color: #182230;
    border-radius: 4px;
    padding: 6px 28px 6px 24px;
}
QMenu::item:disabled {
    color: #98a2b3;
}
QMenu::separator {
    background: #e4e7ec;
    height: 1px;
    margin: 5px 8px;
}
QToolBar {
    background: #ffffff;
    color: #182230;
    border: 0;
    border-bottom: 1px solid #dfe3e8;
    spacing: 2px;
    padding: 6px 8px;
}
QToolBar::separator {
    background: #dfe3e8;
    margin: 4px 8px;
    width: 1px;
}
QToolButton {
    background: transparent;
    color: #344054;
    border: 1px solid transparent;
    border-radius: 6px;
    min-width: 30px;
    min-height: 28px;
    padding: 2px 7px;
}
QToolButton:hover {
    background: #f1f4f8;
    border-color: #d9dfe8;
}
QToolButton:checked {
    background: #e0ecff;
    border-color: #8db5f2;
    color: #1557b0;
}
QToolButton:disabled {
    color: #a8b0bd;
}
QToolButton#boldButton {
    font-weight: 700;
}
QToolButton#italicButton {
    font-style: italic;
}
QFrame#formulaFrame {
    background: #ffffff;
    border-bottom: 1px solid #dfe3e8;
}
QLineEdit {
    background: #ffffff;
    color: #182230;
    border: 1px solid #cbd2da;
    border-radius: 6px;
    padding: 6px 9px;
    selection-background-color: #2f6feb;
    selection-color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #2f6feb;
}
QLineEdit#nameBox {
    color: #1557b0;
    font-weight: 600;
}
QLineEdit#formulaBar {
    color: #182230;
    border-color: transparent;
    border-left-color: #dfe3e8;
    border-radius: 0;
}
QLineEdit#formulaBar:focus {
    border: 1px solid #2f6feb;
    border-radius: 5px;
}
QLabel#fxLabel {
    color: #667085;
    font-style: italic;
    font-weight: 600;
}
QComboBox {
    background: #ffffff;
    color: #182230;
    border: 1px solid #cbd2da;
    border-radius: 6px;
    min-width: 110px;
    min-height: 26px;
    padding: 3px 26px 3px 9px;
}
QComboBox:hover, QComboBox:focus {
    border-color: #7ca7e8;
}
QComboBox::drop-down {
    background: #f7f9fc;
    border: 0;
    border-left: 1px solid #dfe3e8;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #182230;
    border: 1px solid #cbd2da;
    selection-background-color: #e0ecff;
    selection-color: #1557b0;
}
QTableView#spreadsheet {
    background: #ffffff;
    color: #182230;
    alternate-background-color: #ffffff;
    border: 0;
    gridline-color: #e1e6ed;
    selection-background-color: #dceaff;
    selection-color: #102a56;
}
QTableView#spreadsheet::item {
    color: #182230;
    padding: 3px 7px;
}
QTableView#spreadsheet::item:selected {
    border: 1px solid #2f6feb;
}
QHeaderView::section {
    background: #f5f7fa;
    color: #475467;
    border: 0;
    border-right: 1px solid #dfe3e8;
    border-bottom: 1px solid #dfe3e8;
    padding: 4px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #eef1f5;
    border: 0;
    border-right: 1px solid #dfe3e8;
    border-bottom: 1px solid #dfe3e8;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #dfe3e8;
    color: #4b5563;
}
QStatusBar QLabel {
    padding: 2px 10px;
}
QLabel#statusPosition {
    font-weight: 600;
    color: #174ea6;
}
QLabel#documentState {
    color: #667085;
}
QPushButton {
    background: #ffffff;
    color: #182230;
    border: 1px solid #cbd2da;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover {
    background: #eef2f7;
}
QPushButton:default {
    background: #2f6feb;
    border-color: #2f6feb;
    color: #ffffff;
}
QPlainTextEdit {
    background: #ffffff;
    color: #182230;
    border: 1px solid #cbd2da;
    border-radius: 6px;
    selection-background-color: #2f6feb;
    selection-color: #ffffff;
}
QDialog {
    background: #f6f8fb;
}
QScrollBar:vertical {
    background: #f3f5f8;
    border: 0;
    width: 13px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #c6cdd7;
    border-radius: 5px;
    min-height: 32px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #9da8b7;
}
QScrollBar:horizontal {
    background: #f3f5f8;
    border: 0;
    height: 13px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #c6cdd7;
    border-radius: 5px;
    min-width: 32px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #9da8b7;
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: 0;
    width: 0;
    height: 0;
}
QToolTip {
    background: #182230;
    color: #ffffff;
    border: 1px solid #344054;
    padding: 4px 6px;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f6f8fb"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#182230"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f8fafc"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#182230"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#182230"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#182230"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#dceaff"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#102a56"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#98a2b3"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#eef1f5"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#cbd2da"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#667085"))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#344054"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#98a2b3"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#98a2b3"))
    app.setPalette(palette)
    font = QFont("Segoe UI" if sys.platform == "win32" else "Inter")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
