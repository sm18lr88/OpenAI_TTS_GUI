from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QTextEdit,
    QWidget,
)

from ..config import settings
from ..core.text import split_text
from ._layout import about_html, build_central_widget, build_menubar

if TYPE_CHECKING:
    from .workers import TTSWorker

logger = logging.getLogger(__name__)


class TTSWindow(QMainWindow):
    tts_complete = pyqtSignal(str)
    tts_error = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    parallelism_updated = pyqtSignal(int, int)

    text_edit: QTextEdit
    char_count_label: QLabel
    chunk_count_label: QLabel
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

    def __init__(self):
        super().__init__()
        self._api_key: str | None = None
        self._about_html_cache: str | None = None
        self._parallelism = settings.PARALLELISM
        self._parallelism_warning_shown = False
        self.tts_processor: TTSWorker | None = None
        self._startup_api_key_notice_shown = False

        self._init_ui()
        QTimer.singleShot(0, self._finish_startup)

    @pyqtSlot()
    def _finish_startup(self) -> None:
        self._load_initial_api_key()
        self._check_api_key_on_startup()

    def _dialogs_suppressed(self) -> bool:
        return bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI"))

    def _load_initial_api_key(self) -> None:
        from ..keystore import read_api_key

        self._api_key = read_api_key()
        if self._api_key:
            logger.info("API key loaded on initialization.")
        else:
            logger.warning("No API key found on initialization.")

    def _init_ui(self) -> None:
        self.setWindowTitle(settings.APP_NAME)
        self.resize(settings.DEFAULT_WINDOW_WIDTH, settings.DEFAULT_WINDOW_HEIGHT)

        self.stack = build_central_widget(self)
        self.setCentralWidget(self.stack)
        build_menubar(self)

        self._connect_signals()
        self._load_app_settings()
        self.update_counts()
        self.update_instructions_enabled()
        self._refresh_request_ids_button()

        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage("Ready")

    def _connect_signals(self) -> None:
        self.text_edit.textChanged.connect(self.update_counts)
        self.select_path_button.clicked.connect(self.select_save_path)
        self.create_button.clicked.connect(self.start_tts_creation)
        self.cancel_button.clicked.connect(self.cancel_tts_creation)
        self.model_combo.currentIndexChanged.connect(self.update_instructions_enabled)
        self.manage_presets_button.clicked.connect(self.open_preset_dialog)
        self.format_combo.currentTextChanged.connect(self._update_path_extension)
        self.progress_updated.connect(self._update_progress_bar)
        self.parallelism_updated.connect(self._handle_parallelism_update)
        self.tts_complete.connect(self._handle_tts_success)
        self.tts_error.connect(self._handle_tts_error)
        self.retain_files_action.toggled.connect(self._handle_retain_files_toggled)

    def _load_app_settings(self) -> None:
        from ..config import load_app_settings

        persisted = load_app_settings()
        self._parallelism = int(persisted.get("parallelism", settings.PARALLELISM))
        self._parallelism_warning_shown = bool(persisted.get("parallelism_warning_shown", False))
        self.retain_files_action.setChecked(bool(persisted.get("retain_files", False)))

    def _save_app_settings(self) -> None:
        from ..config import save_app_settings

        save_app_settings(
            {
                "parallelism": self._parallelism,
                "parallelism_warning_shown": self._parallelism_warning_shown,
                "retain_files": self.retain_files_action.isChecked(),
            }
        )

    def _effective_parallelism_for_text(self) -> int:
        text = self.text_edit.toPlainText()
        chunks = split_text(text, settings.MAX_CHUNK_SIZE) if text else []
        return min(self._parallelism, len(chunks)) if chunks else 0

    def _update_parallelism_labels(
        self,
        *,
        active_workers: int | None = None,
        worker_cap: int | None = None,
        last_used: int | None = None,
    ) -> None:
        effective_parallelism = self._effective_parallelism_for_text()
        self.parallelism_label.setText(
            f"Parallel workers: up to {self._parallelism}"
            f" (current text uses {effective_parallelism})"
        )
        if active_workers is not None and worker_cap is not None:
            self.parallelism_status_label.setText(
                f"Active chunk workers: {active_workers}/{worker_cap}"
            )
            return
        if last_used is not None:
            self.parallelism_status_label.setText(f"Last run parallelism used: {last_used}")
            return
        self.parallelism_status_label.setText("Active chunk workers: idle")

    @pyqtSlot(bool)
    def _handle_retain_files_toggled(self, _checked: bool) -> None:
        self._save_app_settings()

    @pyqtSlot()
    def _set_parallelism(self) -> None:
        previous_value = self._parallelism
        value, ok = QInputDialog.getInt(
            self,
            "Chunk Parallelism",
            "How many chunks may run at once?",
            value=self._parallelism,
            min=1,
            max=8,
        )
        if not ok:
            return
        self._parallelism = value
        showed_warning = False
        if value > 1 and value > previous_value and not self._parallelism_warning_shown:
            self._parallelism_warning_shown = True
            showed_warning = True
        self._save_app_settings()
        self._update_parallelism_labels()
        if showed_warning:
            self._notify(
                "Parallel Processing Risk",
                "Chunk parallelism was increased above 1. Higher values can trigger rate limits, "
                "may slow down jobs through retries, and are often best kept at 2 or 3 unless your "
                "account stays stable.",
                level="warning",
            )
            return
        self._notify("Parallelism Updated", f"Chunk parallelism set to {value}.")

    def _default_output_path(self, selected_format: str) -> str:
        os.makedirs(settings.DEFAULT_OUTPUT_DIR, exist_ok=True)
        ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        candidate = Path(settings.DEFAULT_OUTPUT_DIR) / f"output{ext}"
        if not candidate.exists():
            return str(candidate)
        for index in range(1, 10_000):
            candidate = Path(settings.DEFAULT_OUTPUT_DIR) / f"output-{index}{ext}"
            if not candidate.exists():
                return str(candidate)
        return str(Path(settings.DEFAULT_OUTPUT_DIR) / f"output-{os.getpid()}{ext}")

    def _normalize_output_path(self, current_path: str, selected_format: str) -> str:
        path = (current_path or "").strip()
        if not path:
            return self._default_output_path(selected_format)
        normalized = Path(path)
        required_ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        if normalized.suffix.lower() != required_ext.lower():
            normalized = normalized.with_suffix(required_ext)
        return str(normalized)

    def _refresh_request_ids_button(self) -> None:
        output_path = (self.path_entry.text() or "").strip()
        if not output_path:
            self.copy_ids_button.setEnabled(False)
            return
        sidecar = Path(f"{output_path}.json")
        if not sidecar.exists():
            self.copy_ids_button.setEnabled(False)
            return
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            request_ids = [
                item.get("request_id")
                for item in data.get("request_meta", [])
                if isinstance(item, dict) and item.get("request_id")
            ]
        except Exception:
            request_ids = []
        self.copy_ids_button.setEnabled(bool(request_ids))

    @pyqtSlot()
    def _load_api_key_from_file(self) -> None:
        from ..keystore import read_api_key

        key = read_api_key()
        if key:
            self._api_key = key
            self._notify("API Key Reloaded", "API key loaded.")
        else:
            self._notify("API Key Not Found", "No API key found.", level="warning")

    @pyqtSlot()
    def _set_custom_api_key(self) -> None:
        from ..keystore import save_api_key

        current = self._api_key or ""
        api_key, ok = QInputDialog.getText(
            self,
            "Set OpenAI API Key",
            "Enter your OpenAI API key (stored in keyring when available):",
            QLineEdit.EchoMode.Password,
            current,
        )
        if not ok:
            return
        api_key = (api_key or "").strip()
        if not api_key:
            self._notify("Empty Key", "API key cannot be empty.", level="warning")
            return
        if save_api_key(api_key):
            self._api_key = api_key
            self._notify("API Key Set", "API key saved.")
        else:
            self._notify("Error", "Failed to save API key.", level="critical")

    def _check_api_key_on_startup(self) -> None:
        if self._api_key or self._startup_api_key_notice_shown:
            return
        self._startup_api_key_notice_shown = True
        self._notify(
            "API Key Missing",
            "No OpenAI API key found. Set one in the 'API Key' menu.",
            level="warning",
        )

    def _notify(self, title: str, message: str, level: str = "info") -> None:
        logger_fn = {
            "info": logger.info,
            "warning": logger.warning,
            "critical": logger.error,
        }.get(level, logger.info)
        logger_fn("%s: %s", title, message)
        with suppress(Exception):
            status_bar: QStatusBar | None = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(f"{title}: {message}", 5000)
        if self._dialogs_suppressed():
            return
        if level == "warning":
            QMessageBox.warning(self, title, message)
        elif level == "critical":
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.information(self, title, message)

    @pyqtSlot()
    def update_counts(self) -> None:
        text = self.text_edit.toPlainText()
        chars = len(text)
        chunks = split_text(text, settings.MAX_CHUNK_SIZE) if text else []
        self.char_count_label.setText(f"Character Count: {chars}")
        self.chunk_count_label.setText(
            f"Chunks (max {settings.MAX_CHUNK_SIZE} chars): {len(chunks)}"
        )
        self._update_parallelism_labels()

    @pyqtSlot()
    def update_instructions_enabled(self) -> None:
        is_gpt4o_mini = self.model_combo.currentText() == settings.GPT_4O_MINI_TTS_MODEL
        self.instructions_edit.setEnabled(is_gpt4o_mini and self.create_button.isEnabled())
        self.instructions_label.setEnabled(is_gpt4o_mini)
        self.manage_presets_button.setEnabled(is_gpt4o_mini and self.create_button.isEnabled())

    @pyqtSlot(str)
    def _update_path_extension(self, selected_format: str) -> None:
        current_path = self.path_entry.text()
        if not current_path:
            return
        self.path_entry.setText(self._normalize_output_path(current_path, selected_format))
        self._refresh_request_ids_button()

    @pyqtSlot(int)
    def _update_progress_bar(self, value: int) -> None:
        self.progress_bar.setValue(value)

    @pyqtSlot()
    def _show_about_page(self) -> None:
        if self._about_html_cache is None:
            self._about_html_cache = about_html()
            self.about_text.setHtml(self._about_html_cache)
        self.stack.setCurrentWidget(self.about_page)
        self.about_back_button.setFocus()

    @pyqtSlot()
    def _show_main_page(self) -> None:
        self.stack.setCurrentIndex(0)
        self.text_edit.setFocus()

    @pyqtSlot()
    def select_save_path(self) -> None:
        selected_format = self.format_combo.currentText()
        file_filter = settings.FORMAT_FILTER_MAP.get(
            selected_format,
            settings.FORMAT_FILTER_MAP["all"],
        )
        current_path = self.path_entry.text()
        start_dir = os.path.dirname(current_path) if current_path else settings.DEFAULT_OUTPUT_DIR
        os.makedirs(start_dir, exist_ok=True)
        default_ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        start_path = current_path or os.path.join(start_dir, f"output{default_ext}")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save TTS Audio As",
            start_path,
            file_filter,
        )
        if not file_path:
            return
        self.path_entry.setText(self._normalize_output_path(file_path, selected_format))
        self._refresh_request_ids_button()

    @pyqtSlot()
    def open_preset_dialog(self) -> None:
        from .dialogs import PresetDialog

        dialog = PresetDialog(self.instructions_edit.toPlainText(), self)
        dialog.preset_selected.connect(self._apply_preset)
        dialog.exec()

    def _apply_preset(self, instructions: str) -> None:
        self.instructions_edit.setPlainText(instructions)

    @pyqtSlot()
    def cancel_tts_creation(self) -> None:
        proc = self.tts_processor
        if proc is None or not proc.isRunning():
            return
        proc.cancel()
        self.cancel_button.setEnabled(False)
        with suppress(Exception):
            status_bar: QStatusBar | None = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage("Cancelling...", 5000)

    def start_tts_creation(self) -> None:
        from .workers import TTSWorker

        if self.tts_processor is not None and self.tts_processor.isRunning():
            self._notify(
                "Already Running",
                "A TTS generation is already in progress.",
                level="warning",
            )
            return

        if not self._api_key:
            self._notify(
                "API Key Missing",
                "Set your OpenAI API key in the 'API Key' menu.",
                level="warning",
            )
            return

        text_to_speak = self.text_edit.toPlainText()
        if not text_to_speak.strip():
            self._notify("Empty Text", "Please enter some text.", level="warning")
            return

        selected_format = self.format_combo.currentText()
        output_path = self._normalize_output_path(self.path_entry.text(), selected_format)
        self.path_entry.setText(output_path)

        output_path_obj = Path(output_path)
        if output_path_obj.exists() and output_path_obj.is_dir():
            self._notify("Path Error", "Output path points to a directory.", level="critical")
            return

        try:
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._notify("Directory Error", str(exc), level="critical")
            return

        try:
            speed_val = float(self.speed_input.text().strip())
            if not math.isfinite(speed_val):
                raise ValueError("Speed must be finite")
            if not (settings.MIN_SPEED <= speed_val <= settings.MAX_SPEED):
                raise ValueError("Speed out of range")
        except ValueError:
            speed_val = settings.DEFAULT_SPEED
            self.speed_input.setText(str(speed_val))
            self._notify(
                "Invalid Speed",
                f"Speed must be between {settings.MIN_SPEED} and {settings.MAX_SPEED}. "
                f"Using {settings.DEFAULT_SPEED}.",
                level="warning",
            )

        selected_model = self.model_combo.currentText()
        instructions_text = ""
        if selected_model == settings.GPT_4O_MINI_TTS_MODEL:
            instructions_text = self.instructions_edit.toPlainText().strip()

        params = {
            "api_key": self._api_key,
            "text": text_to_speak,
            "output_path": output_path,
            "model": selected_model,
            "voice": self.voice_combo.currentText(),
            "response_format": selected_format,
            "speed": speed_val,
            "instructions": instructions_text,
            "parallelism": self._parallelism,
            "retain_files": self.retain_files_action.isChecked(),
        }

        self._set_ui_enabled(False)
        self.cancel_button.setEnabled(True)
        self.copy_ids_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self._update_parallelism_labels(
            active_workers=0,
            worker_cap=min(
                self._parallelism, len(split_text(text_to_speak, settings.MAX_CHUNK_SIZE))
            ),
        )
        self.tts_processor = TTSWorker(params)
        self.tts_processor.progress_updated.connect(self.progress_updated.emit)
        self.tts_processor.parallelism_updated.connect(self.parallelism_updated.emit)
        self.tts_processor.tts_complete.connect(self.tts_complete.emit)
        self.tts_processor.tts_error.connect(self.tts_error.emit)
        self.tts_processor.status_update.connect(self._handle_status_update)
        self.tts_processor.start()

    def _set_ui_enabled(self, enabled: bool) -> None:
        self.text_edit.setEnabled(enabled)
        self.model_combo.setEnabled(enabled)
        self.voice_combo.setEnabled(enabled)
        self.speed_input.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.instructions_edit.setEnabled(
            enabled and self.model_combo.currentText() == settings.GPT_4O_MINI_TTS_MODEL
        )
        self.manage_presets_button.setEnabled(
            enabled and self.model_combo.currentText() == settings.GPT_4O_MINI_TTS_MODEL
        )
        self.path_entry.setEnabled(enabled)
        self.select_path_button.setEnabled(enabled)
        self.create_button.setEnabled(enabled)
        with suppress(Exception):
            menubar: QMenuBar | None = self.menuBar()
            if menubar is not None:
                menubar.setEnabled(enabled)

    @pyqtSlot(str)
    def _handle_tts_success(self, message: str) -> None:
        self._set_ui_enabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(100)
        self._refresh_request_ids_button()
        self._update_parallelism_labels(last_used=self._read_parallelism_used())
        self._notify("TTS Complete", message)
        self.tts_processor = None
        if not self._dialogs_suppressed():
            r = QMessageBox.question(
                self,
                "Open Folder?",
                "Open the output folder now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r == QMessageBox.StandardButton.Yes:
                self._open_containing_folder(self.path_entry.text().strip())

    @pyqtSlot(str)
    def _handle_tts_error(self, error_message: str) -> None:
        self._set_ui_enabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self._refresh_request_ids_button()
        self._update_parallelism_labels()
        self.tts_processor = None

        lower = error_message.lower()
        if "cancel" in lower:
            self._notify("TTS Cancelled", error_message, level="warning")
        else:
            self._notify("TTS Error", error_message, level="critical")

    @pyqtSlot(str)
    def _handle_status_update(self, status: str) -> None:
        with suppress(Exception):
            status_bar: QStatusBar | None = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(status, 5000)

    @pyqtSlot(int, int)
    def _handle_parallelism_update(self, active_workers: int, worker_cap: int) -> None:
        self._update_parallelism_labels(active_workers=active_workers, worker_cap=worker_cap)

    def _read_parallelism_used(self) -> int | None:
        output_path = (self.path_entry.text() or "").strip()
        if not output_path:
            return None
        sidecar = Path(f"{output_path}.json")
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            return None
        value = data.get("parallelism_used")
        return value if isinstance(value, int) else None

    @pyqtSlot()
    def _copy_request_ids(self) -> None:
        output_path = (self.path_entry.text() or "").strip()
        if not output_path:
            self._notify("No Output", "Generate TTS first to copy request IDs.", level="warning")
            return
        sidecar = Path(f"{output_path}.json")
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            reqs = []
            seen = set()
            for item in data.get("request_meta", []):
                if not isinstance(item, dict):
                    continue
                request_id = item.get("request_id")
                if request_id and request_id not in seen:
                    reqs.append(request_id)
                    seen.add(request_id)
            if not reqs:
                self._notify("No Request IDs", "No request IDs found in sidecar.", level="warning")
                return
            clip = QApplication.clipboard()
            if clip is not None:
                clip.setText("\n".join(reqs))
                self._notify("Copied", "Request IDs copied to clipboard.")
            else:
                self._notify("Copy Failed", "Clipboard unavailable.", level="warning")
        except FileNotFoundError:
            self._notify(
                "Sidecar Missing",
                "Sidecar file not found for this output.",
                level="warning",
            )
        except Exception as exc:
            self._notify("Copy Failed", str(exc), level="critical")

    def _open_containing_folder(self, path: str) -> None:
        try:
            folder = os.path.dirname(path) or "."
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            logger.warning("Failed to open folder: %s", exc)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # type: ignore[override]
        proc = self.tts_processor
        if proc is not None and proc.isRunning():
            r = QMessageBox.question(
                self,
                "Confirm Exit",
                "TTS generation in progress. Exit and cancel it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                if event is not None:
                    event.ignore()
                return
            proc.cancel()
            proc.wait(2000)
        super().closeEvent(event if event is not None else QCloseEvent())
