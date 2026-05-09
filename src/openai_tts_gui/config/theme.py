from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#7890AE"
ACCENT_HOVER = "#8BA1BC"
ACCENT_PRESSED = "#5F7899"

DARK_THEME = {
    "background": QColor("#202327"),
    "panel_background": QColor("#202327"),
    "widget_background": QColor("#282D33"),
    "button_background": QColor("#30363E"),
    "button_hover": QColor("#39404A"),
    "text": QColor("#ECEFF3"),
    "muted_text": QColor("#B3BAC5"),
    "disabled_text": QColor("#7D8794"),
    "button_text": QColor("#ECEFF3"),
    "border": QColor("#444C57"),
    "panel_border": QColor("#353C45"),
    "status_background": QColor("#202327"),
    "status_text": QColor("#B3BAC5"),
    "progress_bar_chunk": QColor(ACCENT),
}

LIGHT_THEME = {
    "background": QColor("#EFF1F5"),
    "panel_background": QColor("#F8FAFC"),
    "widget_background": QColor("#FFFFFF"),
    "button_background": QColor("#DCE0E8"),
    "button_hover": QColor("#E2E8F0"),
    "text": QColor("#334155"),
    "muted_text": QColor("#64748B"),
    "disabled_text": QColor("#8A94A6"),
    "button_text": QColor("#4C4F69"),
    "border": QColor("#BCC0CC"),
    "panel_border": QColor("#CBD5E1"),
    "status_background": QColor("#DCE0E8"),
    "status_text": QColor("#4C4F69"),
    "progress_bar_chunk": QColor(ACCENT),
}


def _theme_color(theme: dict[str, QColor], key: str) -> str:
    return theme[key].name()


def _build_qss(theme: dict[str, QColor]) -> str:
    background = _theme_color(theme, "background")
    text = _theme_color(theme, "text")
    muted_text = _theme_color(theme, "muted_text")
    disabled_text = _theme_color(theme, "disabled_text")
    widget_background = _theme_color(theme, "widget_background")
    button_background = _theme_color(theme, "button_background")
    button_hover = _theme_color(theme, "button_hover")
    button_text = _theme_color(theme, "button_text")
    border = _theme_color(theme, "border")
    panel_border = _theme_color(theme, "panel_border")
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
    font-family: "Segoe UI Variable Text", "Segoe UI", "Tahoma", "Arial", sans-serif;
    font-size: 13px;
}}
QGroupBox {{
    background-color: transparent;
    border: none;
    border-radius: 0px;
    margin: 0px;
}}
QLabel#sectionTitle {{
    color: {muted_text};
    font-size: 12px;
    font-weight: 700;
}}
QTextEdit, QLineEdit, QComboBox, QListWidget {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QTextEdit#textEdit {{
    border-color: {panel_border};
    border-radius: 8px;
    font-size: 14px;
    padding: 10px;
}}
QTextEdit:focus, QLineEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QTextEdit:disabled, QLineEdit:disabled, QComboBox:disabled, QListWidget:disabled {{
    color: {disabled_text};
    border-color: {panel_border};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QPushButton {{
    background-color: {button_background};
    color: {button_text};
    border: 1px solid {button_background};
    border-radius: 6px;
    padding: 6px 16px;
    min-width: 80px;
}}
QPushButton:hover {{
    background-color: {button_hover};
    border-color: {button_hover};
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
    border-radius: 7px;
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
QPushButton:disabled {{
    background-color: {widget_background};
    color: {disabled_text};
    border-color: {panel_border};
}}
QLabel#parallelismStatusLabel {{
    color: {muted_text};
}}
QSplitter::handle {{
    background-color: {border};
    height: 3px;
    width: 3px;
}}
QSplitter::handle:hover {{
    background-color: {muted_text};
}}
QToolTip {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
}}
QStatusBar {{
    background-color: transparent;
    color: {status_text};
    border-top: none;
    padding: 2px 8px;
}}
QTextBrowser {{
    background-color: {widget_background};
    color: {text};
    border: 1px solid {border};
    border-radius: 7px;
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
    app.setFont(QFont("Segoe UI Variable Text", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#202327"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#ECEFF3"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#282D33"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#202327"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#282D33"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#ECEFF3"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#ECEFF3"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#30363E"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ECEFF3"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FCA5A5"))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor("#7D8794"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor("#7D8794"),
    )
    app.setPalette(palette)
    app.setStyleSheet(DARK_QSS)
