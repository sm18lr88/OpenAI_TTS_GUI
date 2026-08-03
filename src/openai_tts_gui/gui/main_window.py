from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QWidget,
)

from .. import config
from ._about_page import show_about_page, show_main_page
from ._layout import about_html, build_central_widget, build_menubar
from ._result_actions import ResultActions
from ._run_wiring import RunWiring
from ._window_settings import WindowSettings

if TYPE_CHECKING:
    from .workers import ApiKeyLoadWorker, TTSWorker

logger = logging.getLogger(__name__)


class TTSWindow(QMainWindow):
    tts_complete = pyqtSignal(str)
    tts_error = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    parallelism_updated = pyqtSignal(int, int)

    text_edit: QTextEdit
    char_count_label: QLabel
    chunk_count_label: QLabel
    price_estimate_label: QLabel
    parallelism_label: QLabel
    parallelism_status_label: QLabel
    model_combo: QComboBox
    voice_combo: QComboBox
    speed_input: QLineEdit
    format_combo: QComboBox
    instructions_label: QLabel
    instructions_edit: QTextEdit
    manage_presets_button: QPushButton
    path_entry: QLineEdit
    select_path_button: QPushButton
    progress_bar: QProgressBar
    create_button: QPushButton
    cancel_button: QPushButton
    copy_ids_button: QPushButton
    parallelism_action: QAction
    retain_files_action: QAction
    about_text: QTextBrowser
    about_back_button: QPushButton
    open_log_button: QPushButton
    about_page: QWidget
    stack: QStackedWidget

    def __init__(self) -> None:
        super().__init__()
        self._api_key: str | None = None
        self._about_html_cache: str | None = None
        self._parallelism = config.PARALLELISM
        self._parallelism_warning_shown = False
        self.tts_processor: TTSWorker | None = None
        self._api_key_loader: ApiKeyLoadWorker | None = None
        self._api_key_load_notify = False
        self._startup_api_key_notice_shown = False
        self._close_after_tts_cancel = False
        self._close_after_api_key_load = False
        self._close_retry_timer: QTimer | None = None
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(120)
        self._window_settings = WindowSettings(self)
        self._result_actions = ResultActions(self)
        self._run_wiring = RunWiring(self)
        self._count_timer.timeout.connect(self.update_counts)
        self._init_ui()
        QTimer.singleShot(100, self._finish_startup)

    def _finish_startup(self) -> None:
        if os.environ.get("PYTEST_CURRENT_TEST") or not self.isVisible():
            return
        self._start_api_key_load(notify_on_result=False)

    def _dialogs_suppressed(self) -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI"))

    def _start_api_key_load(self, *, notify_on_result: bool) -> None:
        from .workers import ApiKeyLoadWorker

        if self._api_key_loader is not None and self._api_key_loader.isRunning():
            self._api_key_load_notify = self._api_key_load_notify or notify_on_result
            return
        self._api_key_load_notify = notify_on_result
        self._api_key_loader = ApiKeyLoadWorker(self)
        self._api_key_loader.api_key_loaded.connect(self._handle_api_key_loaded)
        self._api_key_loader.legacy_credential_cleanup_required.connect(
            self._handle_legacy_credential_cleanup
        )
        self._api_key_loader.finished.connect(self._clear_api_key_loader)
        self._api_key_loader.start()

    def _handle_api_key_loaded(self, key: str | None) -> None:
        self._api_key = key or None
        if self._api_key:
            logger.info("API key loaded.")
            if self._api_key_load_notify:
                self._notify("API Key Reloaded", "API key loaded.")
            return
        logger.warning("No API key found.")
        if self._api_key_load_notify:
            self._notify("API Key Not Found", "No API key found.", level="warning")
            return
        self._check_api_key_on_startup()

    @pyqtSlot(str)
    def _handle_legacy_credential_cleanup(self, guidance: str) -> None:
        logger.warning(
            "Legacy credential cleanup required.",
            extra={
                "event": "credential.legacy_cleanup_required",
                "outcome": "stale_legacy_credential",
            },
        )
        (status_bar := self.statusBar()) and status_bar.showMessage(guidance, 10_000)

    def _clear_api_key_loader(self) -> None:
        loader = self._api_key_loader
        self._api_key_loader = None
        self._api_key_load_notify = False
        self._close_after_api_key_load = False
        if loader is not None:
            loader.deleteLater()

    def _init_ui(self) -> None:
        self.setWindowTitle(config.APP_NAME)
        self.resize(config.DEFAULT_WINDOW_WIDTH, config.DEFAULT_WINDOW_HEIGHT)
        self.stack = build_central_widget(self)
        self.setCentralWidget(self.stack)
        build_menubar(self)
        self._connect_signals()
        self._load_app_settings()
        self.update_counts()
        self.update_instructions_enabled()
        self._refresh_request_ids_button()
        (status_bar := self.statusBar()) and status_bar.setSizeGripEnabled(False)
        (status_bar := self.statusBar()) and status_bar.showMessage("Ready")

    def _connect_signals(self) -> None:
        self.text_edit.textChanged.connect(self._schedule_counts_update)
        self.select_path_button.clicked.connect(self.select_save_path)
        self.create_button.clicked.connect(self.start_tts_creation)
        self.cancel_button.clicked.connect(self.cancel_tts_creation)
        self.model_combo.currentIndexChanged.connect(self.update_instructions_enabled)
        self.model_combo.currentIndexChanged.connect(self.update_counts)
        self.manage_presets_button.clicked.connect(self.open_preset_dialog)
        self.format_combo.currentTextChanged.connect(self._update_path_extension)
        self.progress_updated.connect(self._update_progress_bar)
        self.parallelism_updated.connect(self._handle_parallelism_update)
        self.tts_complete.connect(self._handle_tts_success)
        self.tts_error.connect(self._handle_tts_error)
        self.retain_files_action.toggled.connect(self._handle_retain_files_toggled)

    def __getattr__(self, name: str):
        for owner_name in ("_window_settings", "_result_actions", "_run_wiring"):
            owner = self.__dict__.get(owner_name)
            if owner is not None and (method := owner.resolve_legacy(name)) is not None:
                return method
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def _notify(
        self, title: str, message: str, level: str = "info", *, rich_text: bool = False
    ) -> None:
        logger_fn = {"info": logger.info, "warning": logger.warning, "critical": logger.error}.get(
            level, logger.info
        )
        logger_fn("%s: %s", title, message)
        (status_bar := self.statusBar()) and status_bar.showMessage(f"{title}: {message}", 5000)
        if self._dialogs_suppressed():
            return
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(message)
        box.setTextFormat(Qt.TextFormat.RichText if rich_text else Qt.TextFormat.PlainText)
        box.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            if rich_text
            else Qt.TextInteractionFlag.TextSelectableByMouse
        )
        if rich_text:
            self._enable_message_box_external_links(box)
        box.setIcon(
            {"warning": QMessageBox.Icon.Warning, "critical": QMessageBox.Icon.Critical}.get(
                level, QMessageBox.Icon.Information
            )
        )
        box.exec()

    def _enable_message_box_external_links(self, box: QMessageBox) -> None:
        for label in box.findChildren(QLabel):
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

    def _show_about_page(self) -> None:
        show_about_page(self, about_html)

    def _show_main_page(self) -> None:
        show_main_page(self)

    def _schedule_close_retry(self) -> None:
        retry_timer = self._close_retry_timer
        if retry_timer is None:
            retry_timer = QTimer(self)
            retry_timer.setSingleShot(True)
            retry_timer.timeout.connect(self.close)
            self._close_retry_timer = retry_timer
        if not retry_timer.isActive():
            retry_timer.start(50)

    @staticmethod
    def _ignore_close_event(event: QCloseEvent | None) -> None:
        if event is not None:
            event.ignore()

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        loader = self._api_key_loader
        if loader is not None and loader.isRunning():
            if self._close_after_api_key_load:
                self._schedule_close_retry()
                self._ignore_close_event(a0)
                return
            self._close_after_api_key_load = True
            (status_bar := self.statusBar()) and status_bar.showMessage(
                "Waiting for the API key to load before closing...", 5000
            )
            self._schedule_close_retry()
            self._ignore_close_event(a0)
            return
        processor = self.tts_processor
        if processor is not None and processor.isRunning():
            if self._close_after_tts_cancel:
                self._schedule_close_retry()
                self._ignore_close_event(a0)
                return
            response = QMessageBox.question(
                self,
                "Confirm Exit",
                "TTS generation is in progress. Exit and cancel it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                self._ignore_close_event(a0)
                return
            processor.cancel()
            self._close_after_tts_cancel = True
            self.cancel_button.setEnabled(False)
            (status_bar := self.statusBar()) and status_bar.showMessage(
                "Waiting for TTS cancellation to finish before closing...", 5000
            )
            self._schedule_close_retry()
            self._ignore_close_event(a0)
            return
        super().closeEvent(a0 if a0 is not None else QCloseEvent())
