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
    "progress_bar_chunk": QColor(ACCENT),
}

LIGHT_THEME = {
    "background": QColor("#EFF1F5"),
    "text": QColor("#4C4F69"),
    "widget_background": QColor("#FFFFFF"),
    "button_background": QColor("#DCE0E8"),
    "button_text": QColor("#4C4F69"),
    "border": QColor("#BCC0CC"),
    "progress_bar_chunk": QColor(ACCENT),
}

DARK_QSS = f"""
QMainWindow, QDialog {{
    background-color: #1E1E2E;
}}
QWidget {{
    background-color: #1E1E2E;
    color: #CDD6F4;
    font-size: 13px;
}}
QTextEdit, QLineEdit, QComboBox, QListWidget {{
    background-color: #282838;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QPushButton {{
    background-color: #363648;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 6px 16px;
    min-width: 80px;
}}
QPushButton:hover {{
    background-color: #45475A;
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
    background-color: #181825;
    color: #CDD6F4;
    border-bottom: 1px solid #313244;
    padding: 2px;
}}
QMenuBar::item:selected {{
    background-color: #45475A;
    border-radius: 4px;
}}
QMenu {{
    background-color: #282838;
    color: #CDD6F4;
    border: 1px solid #45475A;
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
    border: 1px solid #45475A;
    border-radius: 6px;
    text-align: center;
    color: #CDD6F4;
    background-color: #282838;
    height: 20px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}
QLabel {{
    color: #CDD6F4;
    background-color: transparent;
}}
QSplitter::handle {{
    background-color: #313244;
    height: 2px;
}}
QToolTip {{
    background-color: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 6px;
    padding: 4px 8px;
}}
QStatusBar {{
    background-color: #181825;
    color: #A6ADC8;
    border-top: 1px solid #313244;
}}
QTextBrowser {{
    background-color: #282838;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 6px;
}}
QScrollBar:vertical {{
    background: #1E1E2E;
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: #45475A;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


def build_stylesheet(theme):
    return DARK_QSS


def apply_fusion_dark(app: QApplication):
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
