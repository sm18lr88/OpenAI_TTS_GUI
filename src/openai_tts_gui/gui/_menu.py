from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QMenuBar

if TYPE_CHECKING:
    from .main_window import TTSWindow


def build_menu(window: TTSWindow) -> None:
    menubar: QMenuBar | None = window.menuBar()
    if menubar is None:
        return
    settings_menu: QMenu | None = menubar.addMenu("Settings")
    window.retain_files_action = QAction("Retain intermediate chunk files", window)
    window.retain_files_action.setCheckable(True)
    window.parallelism_action = QAction("Chunk parallelism...", window)
    window.parallelism_action.triggered.connect(window._set_parallelism)
    if settings_menu is not None:
        settings_menu.addAction(window.parallelism_action)
        settings_menu.addAction(window.retain_files_action)
    api_menu: QMenu | None = menubar.addMenu("API Key")
    reload_action = QAction("Reload from secure store", window)
    reload_action.triggered.connect(window._load_api_key_from_file)
    set_key_action = QAction("Set/Update API Key...", window)
    set_key_action.triggered.connect(window._set_custom_api_key)
    if api_menu is not None:
        api_menu.addAction(reload_action)
        api_menu.addAction(set_key_action)
    help_menu: QMenu | None = menubar.addMenu("Help")
    about_action = QAction("About", window)
    about_action.triggered.connect(window._show_about_page)
    back_action = QAction("Back to Application", window)
    back_action.triggered.connect(window._show_main_page)
    if help_menu is not None:
        help_menu.addAction(about_action)
        help_menu.addAction(back_action)
