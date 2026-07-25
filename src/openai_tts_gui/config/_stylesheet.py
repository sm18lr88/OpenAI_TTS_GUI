from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from PyQt6.QtGui import QColor

from ._palette import ACCENT, ACCENT_HOVER, ACCENT_PRESSED, DARK_THEME, LIGHT_THEME


def _theme_color(theme: Mapping[str, QColor], key: str) -> str:
    return theme[key].name()


def _build_qss(theme: Mapping[str, QColor]) -> str:
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


DARK_QSS: Final = _build_qss(DARK_THEME)
LIGHT_QSS: Final = _build_qss(LIGHT_THEME)
REQUIRED_SELECTOR_COLORS: Final = MappingProxyType(
    {
        "QLabel#sectionTitle": MappingProxyType({"color": "#b3bac5"}),
        "QTextEdit#textEdit": MappingProxyType({"border-color": "#353c45"}),
        "QPushButton#primaryButton": MappingProxyType(
            {"background-color": "#7890AE", "color": "#FFFFFF"}
        ),
        "QPushButton#primaryButton:hover": MappingProxyType(
            {"background-color": "#8BA1BC", "border-color": "#8BA1BC"}
        ),
        "QProgressBar::chunk": MappingProxyType({"background-color": "#7890ae"}),
        "QLabel#parallelismStatusLabel": MappingProxyType({"color": "#b3bac5"}),
    }
)


def selector_color_map(stylesheet: str) -> Mapping[str, Mapping[str, str]]:
    semantic_colors: dict[str, Mapping[str, str]] = {}
    for block in stylesheet.split("}"):
        if "{" not in block:
            continue
        selector, declarations = block.split("{", maxsplit=1)
        colors: dict[str, str] = {}
        for declaration in declarations.splitlines():
            line = declaration.strip()
            if not line.endswith(";") or ":" not in line:
                continue
            property_name, value = line[:-1].split(":", maxsplit=1)
            if "color" in property_name or property_name == "background":
                colors[property_name] = value.strip()
        semantic_colors[selector.strip()] = MappingProxyType(colors)
    return MappingProxyType(semantic_colors)


def missing_required_selectors(stylesheet: str) -> tuple[str, ...]:
    actual_selectors = selector_color_map(stylesheet)
    return tuple(
        selector for selector in REQUIRED_SELECTOR_COLORS if selector not in actual_selectors
    )
