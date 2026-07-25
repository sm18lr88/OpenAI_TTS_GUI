from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QStackedWidget

from ._about_page import about_html as about_html
from ._about_page import build_about_page
from ._controls_panel import build_controls_panel
from ._menu import build_menu
from ._text_panel import build_text_panel

if TYPE_CHECKING:
    from .main_window import TTSWindow


def build_central_widget(window: TTSWindow) -> QStackedWidget:
    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(build_text_panel(window))
    splitter.addWidget(build_controls_panel(window))
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([int(window.height() * 0.78), int(window.height() * 0.22)])
    window.about_page = build_about_page(window)
    stack = QStackedWidget()
    stack.addWidget(splitter)
    stack.addWidget(window.about_page)
    return stack


def build_menubar(window: TTSWindow) -> None:
    build_menu(window)
