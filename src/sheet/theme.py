from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

STYLESHEET = """
QMainWindow#mainWindow {
    background: #f4f6f9;
}
QMenuBar {
    background: #ffffff;
    border-bottom: 1px solid #dfe3e8;
    padding: 3px 6px;
}
QMenuBar::item {
    border-radius: 4px;
    padding: 5px 9px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #e8f0fe;
    color: #174ea6;
}
QMenu {
    background: #ffffff;
    border: 1px solid #d7dce2;
    padding: 5px;
}
QMenu::item {
    border-radius: 4px;
    padding: 6px 28px 6px 24px;
}
QToolBar {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #dfe3e8;
    spacing: 3px;
    padding: 4px 8px;
}
QToolBar::separator {
    background: #dfe3e8;
    margin: 4px 7px;
    width: 1px;
}
QToolButton {
    border: 1px solid transparent;
    border-radius: 5px;
    min-width: 28px;
    min-height: 27px;
    padding: 2px 6px;
}
QToolButton:hover {
    background: #eef2f7;
    border-color: #d8dee8;
}
QToolButton:checked {
    background: #dbeafe;
    border-color: #93b4ea;
    color: #174ea6;
}
QFrame#formulaFrame {
    background: #ffffff;
    border-bottom: 1px solid #dfe3e8;
}
QLineEdit {
    background: #ffffff;
    border: 1px solid #cbd2da;
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: #2f6feb;
}
QLineEdit:focus {
    border: 1px solid #2f6feb;
}
QLineEdit#nameBox {
    font-weight: 600;
}
QLineEdit#formulaBar {
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
    border: 1px solid #cbd2da;
    border-radius: 5px;
    min-width: 100px;
    padding: 4px 24px 4px 8px;
}
QTableView#spreadsheet {
    background: #ffffff;
    alternate-background-color: #ffffff;
    border: 0;
    gridline-color: #e3e7ec;
    selection-background-color: #dce9ff;
    selection-color: #172b4d;
}
QTableView#spreadsheet::item {
    padding: 3px 6px;
}
QTableView#spreadsheet::item:selected {
    border: 1px solid #2f6feb;
}
QHeaderView::section {
    background: #f7f8fa;
    color: #4b5563;
    border: 0;
    border-right: 1px solid #dfe3e8;
    border-bottom: 1px solid #dfe3e8;
    padding: 4px;
    font-weight: 600;
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
QPushButton {
    background: #ffffff;
    border: 1px solid #cbd2da;
    border-radius: 5px;
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
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    font = QFont("Inter")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
