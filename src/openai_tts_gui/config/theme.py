from PyQt6.QtGui import QColor

# --- Theme Colors ---
DARK_THEME = {
    "background": QColor("#2E2E2E"),
    "text": QColor("#FFFFFF"),
    "widget_background": QColor("#3E3E3E"),
    "button_background": QColor("#555555"),
    "button_text": QColor("#FFFFFF"),
    "border": QColor("#555555"),
    "progress_bar_chunk": QColor("#66A3FF"),
}

LIGHT_THEME = {
    "background": QColor("#FFFFFF"),
    "text": QColor("#000000"),
    "widget_background": QColor("#F0F0F0"),
    "button_background": QColor("#E0E0E0"),
    "button_text": QColor("#000000"),
    "border": QColor("#CCCCCC"),
    "progress_bar_chunk": QColor("#007BFF"),
}


def build_stylesheet(theme):
    return f"""
        QWidget {{
            background-color: {theme["background"].name()};
            color: {theme["text"].name()};
        }}
        QMainWindow, QDialog {{
            background-color: {theme["background"].name()};
        }}
        QTextEdit, QLineEdit, QComboBox, QListWidget {{
            background-color: {theme["widget_background"].name()};
            color: {theme["text"].name()};
            border: 1px solid {theme["border"].name()};
            padding: 2px;
        }}
        QPushButton {{
            background-color: {theme["button_background"].name()};
            color: {theme["button_text"].name()};
            border: 1px solid {theme["border"].name()};
            padding: 5px;
            min-width: 80px;
        }}
        QPushButton:hover {{
            background-color: {theme["widget_background"].name()};
        }}
        QPushButton:pressed {{
            background-color: {theme["border"].name()};
        }}
        QMenuBar {{
            background-color: {theme["widget_background"].name()};
            color: {theme["text"].name()};
        }}
        QMenuBar::item:selected {{
            background-color: {theme["button_background"].name()};
        }}
        QMenu {{
            background-color: {theme["widget_background"].name()};
            color: {theme["text"].name()};
        }}
        QMenu::item:selected {{
            background-color: {theme["button_background"].name()};
        }}
        QProgressBar {{
            border: 1px solid {theme["border"].name()};
            text-align: center;
            color: {theme["text"].name()};
            background-color: {theme["widget_background"].name()};
        }}
        QProgressBar::chunk {{
            background-color: {theme["progress_bar_chunk"].name()};
            width: 10px;
            margin: 0.5px;
        }}
        QLabel {{
             color: {theme["text"].name()};
        }}
        QSplitter::handle {{
             background-color: {theme["border"].name()};
             height: 3px;
        }}
        QToolTip {{
             background-color: {theme["widget_background"].name()};
             color: {theme["text"].name()};
             border: 1px solid {theme["border"].name()};
        }}
    """
