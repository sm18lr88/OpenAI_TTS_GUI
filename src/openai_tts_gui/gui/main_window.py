import json
import logging
import os
import subprocess
import sys
from contextlib import suppress

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
from ..keystore import read_api_key, save_api_key
from ._layout import about_html, build_central_widget, build_menubar
from .dialogs import PresetDialog
from .workers import TTSWorker

logger = logging.getLogger(__name__)


class TTSWindow(QMainWindow):
    tts_complete = pyqtSignal(str)
    tts_error = pyqtSignal(str)
    progress_updated = pyqtSignal(int)

    text_edit: QTextEdit
    char_count_label: QLabel
    chunk_count_label: QLabel
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
    copy_ids_button: QPushButton
    retain_files_action: QAction
    about_text: QTextBrowser
    about_back_button: QPushButton
    open_log_button: QPushButton
    about_page: QWidget
    stack: QStackedWidget

    def __init__(self):
        super().__init__()
        self._api_key: str | None = None
        self.tts_processor: TTSWorker | None = None

        self._load_initial_api_key()
        self._init_ui()
        self._check_api_key_on_startup()
        QTimer.singleShot(100, self._check_api_key_on_startup)

    def _load_initial_api_key(self):
        self._api_key = read_api_key()
        if self._api_key:
            logger.info("API key loaded on initialization.")
        else:
            logger.warning("No API key found on initialization.")

    def _init_ui(self):
        self.setWindowTitle(settings.APP_NAME)
        self.resize(settings.DEFAULT_WINDOW_WIDTH, settings.DEFAULT_WINDOW_HEIGHT)

        self.stack = build_central_widget(self)
        self.setCentralWidget(self.stack)
        build_menubar(self)

        self._connect_signals()
        self.update_counts()
        self.update_instructions_enabled()

        status_bar = self.statusBar()
        if status_bar:
            status_bar.showMessage("Ready")

    def _connect_signals(self):
        self.text_edit.textChanged.connect(self.update_counts)
        self.select_path_button.clicked.connect(self.select_save_path)
        self.create_button.clicked.connect(self.start_tts_creation)
        self.model_combo.currentIndexChanged.connect(self.update_instructions_enabled)
        self.manage_presets_button.clicked.connect(self.open_preset_dialog)
        self.format_combo.currentTextChanged.connect(self._update_path_extension)
        self.progress_updated.connect(self._update_progress_bar)
        self.tts_complete.connect(self._handle_tts_success)
        self.tts_error.connect(self._handle_tts_error)

    @pyqtSlot()
    def _load_api_key_from_file(self):
        key = read_api_key()
        if key:
            self._api_key = key
            self._notify("API Key Reloaded", "API key loaded.")
        else:
            self._notify("API Key Not Found", "No API key found.", level="warning")

    @pyqtSlot()
    def _set_custom_api_key(self):
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

    def _check_api_key_on_startup(self):
        if not self._api_key:
            self._notify(
                "API Key Missing",
                "No OpenAI API key found. Set one in the 'API Key' menu.",
                level="warning",
            )

    def _notify(self, title: str, message: str, level: str = "info"):
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
        if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI")):
            if level == "warning":
                QMessageBox.warning(self, title, message)
            elif level == "critical":
                QMessageBox.critical(self, title, message)
            else:
                QMessageBox.information(self, title, message)

    @pyqtSlot()
    def update_counts(self):
        text = self.text_edit.toPlainText()
        chars = len(text)
        chunks = split_text(text, settings.MAX_CHUNK_SIZE) if text else []
        self.char_count_label.setText(f"Character Count: {chars}")
        self.chunk_count_label.setText(
            f"Chunks (max {settings.MAX_CHUNK_SIZE} chars): {len(chunks)}"
        )

    @pyqtSlot()
    def update_instructions_enabled(self):
        is_gpt4o_mini = self.model_combo.currentText() == settings.GPT_4O_MINI_TTS_MODEL
        self.instructions_edit.setEnabled(is_gpt4o_mini)
        self.instructions_label.setEnabled(is_gpt4o_mini)
        self.manage_presets_button.setEnabled(is_gpt4o_mini)

    @pyqtSlot(str)
    def _update_path_extension(self, selected_format: str):
        current_path = self.path_entry.text()
        if not current_path:
            return
        path_base, _ = os.path.splitext(current_path)
        new_ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        self.path_entry.setText(path_base + new_ext)

    @pyqtSlot(int)
    def _update_progress_bar(self, value: int):
        self.progress_bar.setValue(value)

    @pyqtSlot()
    def _show_about_page(self):
        self.about_text.setHtml(about_html())
        self.stack.setCurrentWidget(self.about_page)
        self.about_back_button.setFocus()

    @pyqtSlot()
    def _show_main_page(self):
        self.stack.setCurrentIndex(0)
        self.text_edit.setFocus()

    @pyqtSlot()
    def select_save_path(self):
        selected_format = self.format_combo.currentText()
        file_filter = settings.FORMAT_FILTER_MAP.get(
            selected_format, settings.FORMAT_FILTER_MAP["all"]
        )
        current_path = self.path_entry.text()
        start_dir = os.path.dirname(current_path) if current_path else settings.DEFAULT_OUTPUT_DIR
        os.makedirs(start_dir, exist_ok=True)
        default_ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        start_path = os.path.join(start_dir, f"output{default_ext}")

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save TTS Audio As", start_path, file_filter
        )
        if not file_path:
            return
        _, ext = os.path.splitext(file_path)
        required_ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        if ext.lower() != required_ext.lower():
            file_path = os.path.splitext(file_path)[0] + required_ext
        self.path_entry.setText(file_path)

    @pyqtSlot()
    def open_preset_dialog(self):
        dialog = PresetDialog(self.instructions_edit.toPlainText(), self)
        dialog.preset_selected.connect(self._apply_preset)
        dialog.exec()

    def _apply_preset(self, instructions: str):
        self.instructions_edit.setPlainText(instructions)

    def start_tts_creation(self):
        if not self._api_key:
            self._notify(
                "API Key Missing",
                "Set your OpenAI API key in the 'API Key' menu.",
                level="warning",
            )
            return
        text_to_speak = self.text_edit.toPlainText().strip()
        if not text_to_speak:
            self._notify("Empty Text", "Please enter some text.", level="warning")
            return
        output_path = (self.path_entry.text() or "").strip()
        if not output_path:
            selected_format = self.format_combo.currentText()
            default_ext = settings.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
            os.makedirs(settings.DEFAULT_OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(settings.DEFAULT_OUTPUT_DIR, f"output{default_ext}")
            self.path_entry.setText(output_path)

        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self._notify("Directory Error", str(e), level="critical")
                return

        try:
            speed_val = float(self.speed_input.text().strip())
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
            "response_format": self.format_combo.currentText(),
            "speed": speed_val,
            "instructions": instructions_text,
            "retain_files": self.retain_files_action.isChecked(),
        }

        self._set_ui_enabled(False)
        self.progress_bar.setValue(0)
        self.tts_processor = TTSWorker(params)
        self.tts_processor.progress_updated.connect(self.progress_updated.emit)
        self.tts_processor.tts_complete.connect(self.tts_complete.emit)
        self.tts_processor.tts_error.connect(self.tts_error.emit)
        self.tts_processor.status_update.connect(self._handle_status_update)
        self.tts_processor.start()

    def _set_ui_enabled(self, enabled: bool):
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
    def _handle_tts_success(self, message: str):
        self._set_ui_enabled(True)
        self.progress_bar.setValue(100)
        self.copy_ids_button.setEnabled(True)
        self._notify("TTS Complete", message)
        if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CI")):
            r = QMessageBox.question(
                self,
                "Open Folder?",
                "Open the output folder now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r == QMessageBox.StandardButton.Yes:
                self._open_containing_folder(self.path_entry.text().strip())

    @pyqtSlot(str)
    def _handle_tts_error(self, error_message: str):
        self._set_ui_enabled(True)
        self.progress_bar.setValue(0)
        self.copy_ids_button.setEnabled(True)
        self._notify("TTS Error", error_message, level="critical")

    @pyqtSlot(str)
    def _handle_status_update(self, status: str):
        with suppress(Exception):
            status_bar: QStatusBar | None = self.statusBar()
            if status_bar is not None:
                status_bar.showMessage(status, 5000)

    @pyqtSlot()
    def _copy_request_ids(self):
        output_path = (self.path_entry.text() or "").strip()
        if not output_path:
            self._notify("No Output", "Generate TTS first to copy request IDs.", level="warning")
            return
        sidecar = output_path + ".json"
        try:
            with open(sidecar, encoding="utf-8") as f:
                data = json.load(f)
            reqs = [
                r.get("request_id") for r in data.get("request_meta", []) if r.get("request_id")
            ]
            if not reqs:
                self._notify("No Request IDs", "No request IDs found in sidecar.", level="warning")
                return
            ids_text = "\n".join(reqs)
            clip = QApplication.clipboard()
            if clip is not None:
                clip.setText(ids_text)
                self._notify("Copied", "Request IDs copied to clipboard.")
            else:
                self._notify("Copy Failed", "Clipboard unavailable.", level="warning")
        except FileNotFoundError:
            self._notify(
                "Sidecar Missing",
                "Sidecar file not found for this output.",
                level="warning",
            )
        except Exception as e:
            self._notify("Copy Failed", str(e), level="critical")

    def _open_containing_folder(self, path: str):
        try:
            folder = os.path.dirname(path) or "."
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            logger.warning("Failed to open folder: %s", e)

    def closeEvent(self, event: QCloseEvent | None) -> None:  # type: ignore[override]
        proc = getattr(self, "tts_processor", None)
        if proc is not None and hasattr(proc, "isRunning") and proc.isRunning():
            r = QMessageBox.question(
                self,
                "Confirm Exit",
                "TTS generation in progress. Exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r == QMessageBox.StandardButton.Yes:
                if event is not None:
                    event.accept()
            else:
                if event is not None:
                    event.ignore()
                return
        super().closeEvent(event if event is not None else QCloseEvent())
