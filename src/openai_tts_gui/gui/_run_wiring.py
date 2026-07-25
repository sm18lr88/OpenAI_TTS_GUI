from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

from PyQt6.QtWidgets import QMenuBar, QMessageBox, QStatusBar

from .. import config
from ..core import split_text
from ..errors import ConfigError
from ..tts import (
    CancelledOutcome,
    ChunkFailureOutcome,
    DestinationChangedOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    GenerationOutcome,
    OutputBusyOutcome,
    ProviderFailureOutcome,
    PublicationFailureOutcome,
    PublicationRecoveryFailureOutcome,
    SuccessOutcome,
    UnknownFailureOutcome,
)

if TYPE_CHECKING:
    from .main_window import TTSWindow


class RunWiring:
    _LEGACY_METHODS = {
        "_update_progress_bar": "update_progress_bar",
        "cancel_tts_creation": "cancel_tts_creation",
        "start_tts_creation": "start_tts_creation",
        "_set_ui_enabled": "set_ui_enabled",
        "_handle_tts_success": "handle_tts_success",
        "_handle_tts_error": "handle_tts_error",
        "_handle_status_update": "handle_status_update",
        "_handle_parallelism_update": "handle_parallelism_update",
    }

    def __init__(self, window: TTSWindow) -> None:
        self._window = window

    def resolve_legacy(self, name: str):
        method_name = self._LEGACY_METHODS.get(name)
        return getattr(self, method_name) if method_name is not None else None

    def update_progress_bar(self, value: int) -> None:
        self._window.progress_bar.setValue(value)

    def cancel_tts_creation(self) -> None:
        processor = self._window.tts_processor
        if processor is None or not processor.isRunning():
            return
        processor.cancel()
        self._window.cancel_button.setEnabled(False)

    def start_tts_creation(self) -> None:
        from . import TTSWorker

        if self._window.tts_processor is not None and self._window.tts_processor.isRunning():
            self._window._notify(
                "Already Running", "A TTS generation is already in progress.", level="warning"
            )
            return
        if not self._window._api_key:
            self._window._notify(
                "API Key Missing", "Set your OpenAI API key in the 'API Key' menu.", level="warning"
            )
            return
        text_to_speak = self._window.text_edit.toPlainText()
        if not text_to_speak.strip():
            self._window._notify("Empty Text", "Please enter some text.", level="warning")
            return
        selected_format = self._window.format_combo.currentText()
        output_path = self._window._normalize_output_path(
            self._window.path_entry.text(), selected_format
        )
        self._window.path_entry.setText(output_path)
        output_path_object = Path(output_path)
        if output_path_object.exists() and output_path_object.is_dir():
            self._window._notify(
                "Path Error", "Output path points to a directory.", level="critical"
            )
            return
        try:
            speed = float(self._window.speed_input.text().strip())
            if not math.isfinite(speed):
                raise ConfigError("Speed must be finite")
            if not config.MIN_SPEED <= speed <= config.MAX_SPEED:
                raise ConfigError("Speed out of range")
        except (ConfigError, ValueError):
            speed = config.DEFAULT_SPEED
            self._window.speed_input.setText(str(speed))
            self._window._notify(
                "Invalid Speed",
                f"Speed must be between {config.MIN_SPEED} and {config.MAX_SPEED}. "
                f"Using {config.DEFAULT_SPEED}.",
                level="warning",
            )
        model = self._window.model_combo.currentText()
        instructions = (
            self._window.instructions_edit.toPlainText().strip()
            if model == config.GPT_4O_MINI_TTS_MODEL
            else ""
        )
        params = {
            "api_key": self._window._api_key,
            "text": text_to_speak,
            "output_path": output_path,
            "model": model,
            "voice": self._window.voice_combo.currentText(),
            "response_format": selected_format,
            "speed": speed,
            "instructions": instructions,
            "parallelism": self._window._parallelism,
            "retain_files": self._window.retain_files_action.isChecked(),
        }
        self.set_ui_enabled(False)
        self._window.cancel_button.setEnabled(True)
        self._window.copy_ids_button.setEnabled(False)
        self._window.progress_bar.setValue(0)
        self._window._update_parallelism_labels(
            active_workers=0,
            worker_cap=min(
                self._window._parallelism, len(split_text(text_to_speak, config.MAX_CHUNK_SIZE))
            ),
        )
        worker = TTSWorker(params)
        worker.progress_updated.connect(self._window.progress_updated.emit)
        worker.parallelism_updated.connect(self._window.parallelism_updated.emit)
        worker.terminal_outcome.connect(self.handle_outcome)
        worker.status_update.connect(self.handle_status_update)
        self._window.tts_processor = worker
        worker.start()

    def set_ui_enabled(self, enabled: bool) -> None:
        self._window.text_edit.setEnabled(enabled)
        self._window.model_combo.setEnabled(enabled)
        self._window.voice_combo.setEnabled(enabled)
        self._window.speed_input.setEnabled(enabled)
        self._window.format_combo.setEnabled(enabled)
        self._window.instructions_edit.setEnabled(
            enabled and self._window.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        )
        self._window.manage_presets_button.setEnabled(
            enabled and self._window.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        )
        self._window.path_entry.setEnabled(enabled)
        self._window.select_path_button.setEnabled(enabled)
        self._window.create_button.setEnabled(enabled)
        menubar: QMenuBar | None = self._window.menuBar()
        if menubar is not None:
            menubar.setEnabled(enabled)

    def handle_tts_success(self, message: str) -> None:
        self.set_ui_enabled(True)
        self._window.cancel_button.setEnabled(False)
        self._window.progress_bar.setValue(100)
        self._window._refresh_request_ids_button()
        self._window._update_parallelism_labels(last_used=self._window._read_parallelism_used())
        self._window._notify(
            "TTS Complete", self._window._completion_message(message), rich_text=True
        )
        self._window.tts_processor = None
        if self._window._dialogs_suppressed():
            return
        response = QMessageBox.question(
            self._window,
            "Open Folder?",
            "Open the output folder now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self._window._open_containing_folder(self._window.path_entry.text().strip())

    def handle_tts_error(self, error_message: str) -> None:
        self.set_ui_enabled(True)
        self._window.cancel_button.setEnabled(False)
        self._window.progress_bar.setValue(0)
        self._window._refresh_request_ids_button()
        self._window._update_parallelism_labels()
        self._window.tts_processor = None
        self._window._notify("TTS Error", error_message, level="critical")

    def handle_outcome(self, outcome: GenerationOutcome) -> None:
        match outcome:
            case SuccessOutcome(message=message):
                self.handle_tts_success(message)
            case CancelledOutcome(message=message):
                self._finish_terminal(message, "TTS Cancelled", "warning")
            case ProviderFailureOutcome(message=message) | ChunkFailureOutcome(message=message):
                self._finish_terminal(message, "TTS Error", "critical")
            case FfmpegFailureOutcome(message=message) | FfmpegNotFoundOutcome(message=message):
                self._finish_terminal(message, "TTS Error", "critical")
            case (
                PublicationRecoveryFailureOutcome(message=message)
                | PublicationFailureOutcome(message=message)
            ):
                self._finish_terminal(message, "TTS Error", "critical")
            case UnknownFailureOutcome(message=message):
                self._finish_terminal(message, "TTS Error", "critical")
            case OutputBusyOutcome(output_path=output_path):
                self._finish_terminal(f"Output is busy: {output_path}", "TTS Error", "critical")
            case DestinationChangedOutcome(output_path=output_path, reason=reason):
                self._finish_terminal(
                    f"Output changed: {output_path} ({reason})", "TTS Error", "critical"
                )
            case unreachable:
                assert_never(unreachable)

    def _finish_terminal(self, message: str, title: str, level: str) -> None:
        self.set_ui_enabled(True)
        self._window.cancel_button.setEnabled(False)
        self._window.progress_bar.setValue(0)
        self._window._refresh_request_ids_button()
        self._window._update_parallelism_labels()
        self._window.tts_processor = None
        self._window._notify(title, message, level=level)

    def handle_status_update(self, status: str) -> None:
        status_bar: QStatusBar | None = self._window.statusBar()
        if status_bar is not None:
            status_bar.showMessage(status, 5000)

    def handle_parallelism_update(self, active_workers: int, worker_cap: int) -> None:
        self._window._update_parallelism_labels(
            active_workers=active_workers, worker_cap=worker_cap
        )
