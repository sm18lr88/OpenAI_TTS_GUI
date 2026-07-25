from __future__ import annotations

from PyQt6.QtGui import QFont, QPalette
from PyQt6.QtWidgets import QApplication

from ._palette import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    DARK_DISABLED_FUSION_PALETTE,
    DARK_FUSION_PALETTE,
    DARK_THEME,
    LIGHT_THEME,
)
from ._stylesheet import DARK_QSS, LIGHT_QSS

__all__ = [
    "ACCENT",
    "ACCENT_HOVER",
    "ACCENT_PRESSED",
    "DARK_QSS",
    "DARK_THEME",
    "LIGHT_QSS",
    "LIGHT_THEME",
    "apply_fusion_dark",
    "build_stylesheet",
]


def build_stylesheet(theme) -> str:
    if theme == LIGHT_THEME:
        return LIGHT_QSS
    return DARK_QSS


def apply_fusion_dark(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable Text", 10))
    palette = QPalette()
    for role, color in DARK_FUSION_PALETTE.items():
        palette.setColor(role, color)
    for role, color in DARK_DISABLED_FUSION_PALETTE.items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, color)
    app.setPalette(palette)
    app.setStyleSheet(DARK_QSS)
