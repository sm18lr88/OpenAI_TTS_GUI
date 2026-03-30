from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#5B9CF5"
ACCENT_HOVER = "#7DB3FF"
ACCENT_PRESSED = "#4080D4"

DARK_THEME = {
    "background": QColor("#1E1E2E"),
    "text": QColor("#CDD6F4"),
    "widget_background": QColor("#282838"),
    "button_background": QColor("#363648"),
    "button_text": QColor("#CDD6F4"),
    "border": QColor("#45475A"),
    "status_background": QColor("#181825"),
    "status_text": QColor("#A6ADC8"),
    "progress_bar_chunk": QColor(ACCENT),
}

LIGHT_THEME = {
    "background": QColor("#EFF1F5"),
    "text": QColor("#4C4F69"),
    "widget_background": QColor("#FFFFFF"),
    "button_background": QColor("#DCE0E8"),
    "button_text": QColor("#4C4F69"),
    "border": QColor("#BCC0CC"),
    "status_background": QColor("#DCE0E8"),
    "status_text": QColor("#4C4F69"),
    "progress_bar_chunk": QColor(ACCENT),
}


def _theme_color(theme: dict[str, QColor], key: str) -> str:
    return theme[key].name()


def _build_qss(theme: dict[str, QColor]) -> str:
    background = _theme_color(theme, "background")
    text = _theme_color(theme, "text")
    widget_background = _theme_color(theme, "widget_background")
    button_background = _theme_color(theme, "button_background")
    button_text = _theme_color(theme, "button_text")
    border = _theme_color(theme, "border")
    status_background = _theme_color(theme, "status_background")
    status_text = _theme_color(theme, "status_text")
    progress_chunk = _theme_color(theme, "progress_bar_chunk")

    return f"""
QMainWindow, QDialog {{
    background-color: {background};
}}
QWidget {{
    background-color: {background};
    color: {text};
    font-size: 13px;
}}
QTextEdit, QLineEdit, QComboBox, QListWidget {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QPushButton {{
    background-color: {button_background};
    color: {button_text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 16px;
    min-width: 80px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_PRESSED};
    color: #FFFFFF;
}}
QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: #FFFFFF;
    border: 1px solid {ACCENT};
    font-weight: bold;
}}
QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:pressed {{
    background-color: {ACCENT_PRESSED};
}}
QMenuBar {{
    background-color: {status_background};
    color: {text};
    border-bottom: 1px solid {border};
    padding: 2px;
}}
QMenuBar::item:selected {{
    background-color: {border};
    border-radius: 4px;
}}
QMenu {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: #FFFFFF;
}}
QProgressBar {{
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    color: {text};
    background-color: {widget_background};
    height: 20px;
}}
QProgressBar::chunk {{
    background-color: {progress_chunk};
    border-radius: 5px;
}}
QLabel {{
    color: {text};
    background-color: transparent;
}}
QSplitter::handle {{
    background-color: {border};
    height: 2px;
}}
QToolTip {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
}}
QStatusBar {{
    background-color: {status_background};
    color: {status_text};
    border-top: 1px solid {border};
}}
QTextBrowser {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
}}
QScrollBar:vertical {{
    background: {background};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
""".strip()


DARK_QSS = _build_qss(DARK_THEME)
LIGHT_QSS = _build_qss(LIGHT_THEME)


def build_stylesheet(theme):
    if theme == LIGHT_THEME:
        return LIGHT_QSS
    return DARK_QSS


def apply_fusion_dark(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1E1E2E"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#282838"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#363648"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#CDD6F4"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#F38BA8"))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6C7086"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6C7086"))
    app.setPalette(palette)
    app.setStyleSheet(DARK_QSS)
