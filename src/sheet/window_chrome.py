from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QComboBox, QToolBar, QToolButton

if TYPE_CHECKING:
    from sheet.window import MainWindow


def build_menus(window: MainWindow) -> None:
    file_menu = window.menuBar().addMenu("&File")
    file_menu.addActions(
        [window.new_action, window.open_action, window.save_action, window.save_as_action]
    )
    file_menu.addSeparator()
    file_menu.addActions([window.import_csv_action, window.export_csv_action])
    file_menu.addSeparator()
    file_menu.addAction(window.quit_action)

    edit_menu = window.menuBar().addMenu("&Edit")
    edit_menu.addActions([window.undo_action, window.redo_action])
    edit_menu.addSeparator()
    edit_menu.addActions(
        [
            window.cut_action,
            window.copy_action,
            window.paste_action,
            window.delete_action,
            window.select_all_action,
            window.find_replace_action,
        ]
    )

    format_menu = window.menuBar().addMenu("F&ormat")
    format_menu.addActions([window.bold_action, window.italic_action])
    alignment_menu = format_menu.addMenu("Alignment")
    alignment_menu.addActions(list(window.alignment_actions.values()))

    sheet_menu = window.menuBar().addMenu("&Sheet")
    sheet_menu.addActions([window.insert_rows_action, window.delete_rows_action])
    sheet_menu.addActions([window.insert_columns_action, window.delete_columns_action])
    sheet_menu.addSeparator()
    sheet_menu.addActions([window.sort_ascending_action, window.sort_descending_action])
    sheet_menu.addSeparator()
    sheet_menu.addActions([window.add_rows_action, window.add_columns_action])

    python_menu = window.menuBar().addMenu("&Python")
    python_menu.addAction(window.script_action)
    window.view_menu = window.menuBar().addMenu("&View")


def build_toolbars(window: MainWindow) -> None:
    main_toolbar = _main_toolbar(window)
    format_toolbar = _format_toolbar(window)
    window.addToolBar(main_toolbar)
    window.addToolBar(format_toolbar)
    window.view_menu.addAction(main_toolbar.toggleViewAction())
    window.view_menu.addAction(format_toolbar.toggleViewAction())


def _main_toolbar(window: MainWindow) -> QToolBar:
    toolbar = _toolbar("Main", "mainToolbar", window)
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    toolbar.addActions([window.new_action, window.open_action, window.save_action])
    toolbar.addSeparator()
    toolbar.addActions([window.undo_action, window.redo_action])
    toolbar.addSeparator()
    toolbar.addAction(window.script_action)
    return toolbar


def _format_toolbar(window: MainWindow) -> QToolBar:
    toolbar = _toolbar("Formatting", "formatToolbar", window)
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    toolbar.addActions([window.bold_action, window.italic_action])
    _style_format_buttons(toolbar, window)
    toolbar.addSeparator()
    toolbar.addActions(list(window.alignment_actions.values()))
    toolbar.addSeparator()
    window.number_format = _number_format_box(window)
    toolbar.addWidget(window.number_format)
    return toolbar


def _toolbar(title: str, object_name: str, window: MainWindow) -> QToolBar:
    toolbar = QToolBar(title, window)
    toolbar.setObjectName(object_name)
    toolbar.setMovable(False)
    toolbar.setIconSize(QSize(19, 19))
    return toolbar


def _style_format_buttons(toolbar: QToolBar, window: MainWindow) -> None:
    bold_button = toolbar.widgetForAction(window.bold_action)
    italic_button = toolbar.widgetForAction(window.italic_action)
    if isinstance(bold_button, QToolButton):
        bold_button.setObjectName("boldButton")
        bold_button.setText("B")
    if isinstance(italic_button, QToolButton):
        italic_button.setObjectName("italicButton")
        italic_button.setText("I")


def _number_format_box(window: MainWindow) -> QComboBox:
    number_format = QComboBox()
    number_format.setObjectName("numberFormat")
    number_format.setToolTip("Number format")
    number_format.addItem("General", "general")
    number_format.addItem("Number", "number")
    number_format.addItem("Currency", "currency")
    number_format.addItem("Percent", "percent")
    number_format.currentIndexChanged.connect(window._number_format_changed)
    return number_format
