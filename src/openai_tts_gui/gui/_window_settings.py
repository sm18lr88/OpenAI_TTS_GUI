from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QLineEdit

from .. import config
from ..core import split_text

if TYPE_CHECKING:
    from .main_window import TTSWindow


class WindowSettings:
    _LEGACY_METHODS = {
        "_load_app_settings": "load_app_settings",
        "_save_app_settings": "save_app_settings",
        "_effective_parallelism_for_text": "effective_parallelism_for_text",
        "_update_parallelism_labels": "update_parallelism_labels",
        "_handle_retain_files_toggled": "handle_retain_files_toggled",
        "_set_parallelism": "set_parallelism",
        "_schedule_counts_update": "schedule_counts_update",
        "update_counts": "update_counts",
        "_format_price_estimate": "format_price_estimate",
        "_character_price": "character_price",
        "_gpt_4o_mini_tts_estimate": "gpt_4o_mini_tts_estimate",
        "_format_usd": "format_usd",
        "update_instructions_enabled": "update_instructions_enabled",
        "_update_path_extension": "update_path_extension",
        "_default_output_path": "default_output_path",
        "_normalize_output_path": "normalize_output_path",
        "select_save_path": "select_save_path",
        "_set_custom_api_key": "set_custom_api_key",
        "_check_api_key_on_startup": "check_api_key_on_startup",
        "_load_api_key_from_file": "load_api_key_from_file",
        "open_preset_dialog": "open_preset_dialog",
        "_apply_preset": "apply_preset",
    }

    def __init__(self, window: TTSWindow) -> None:
        self._window = window

    def resolve_legacy(self, name: str):
        method_name = self._LEGACY_METHODS.get(name)
        return getattr(self, method_name) if method_name is not None else None

    def load_app_settings(self) -> None:
        persisted = config.load_app_settings()
        self._window._parallelism = int(persisted.get("parallelism", config.PARALLELISM))
        self._window._parallelism_warning_shown = bool(
            persisted.get("parallelism_warning_shown", False)
        )
        self._window.retain_files_action.setChecked(bool(persisted.get("retain_files", False)))

    def save_app_settings(self) -> None:
        config.save_app_settings(
            {
                "parallelism": self._window._parallelism,
                "parallelism_warning_shown": self._window._parallelism_warning_shown,
                "retain_files": self._window.retain_files_action.isChecked(),
            }
        )

    def effective_parallelism_for_text(self) -> int:
        text = self._window.text_edit.toPlainText()
        chunks = split_text(text, config.MAX_CHUNK_SIZE) if text else []
        return min(self._window._parallelism, len(chunks)) if chunks else 0

    def update_parallelism_labels(
        self,
        *,
        active_workers: int | None = None,
        worker_cap: int | None = None,
        last_used: int | None = None,
    ) -> None:
        effective_parallelism = self.effective_parallelism_for_text()
        self._window.parallelism_label.setText(
            f"Parallel workers: {effective_parallelism} (max: {self._window._parallelism})"
        )
        if active_workers is not None and worker_cap is not None:
            self._window.parallelism_status_label.setText(
                f"Active chunk workers: {active_workers}/{worker_cap}"
            )
            return
        if last_used is not None:
            self._window.parallelism_status_label.setText(f"Last run parallelism used: {last_used}")
            return
        self._window.parallelism_status_label.setText("Active chunk workers: idle")

    def handle_retain_files_toggled(self, _checked: bool) -> None:
        self.save_app_settings()

    def set_parallelism(self) -> None:
        previous_value = self._window._parallelism
        value, ok = QInputDialog.getInt(
            self._window,
            "Chunk Parallelism",
            "How many chunks may run at once?",
            value=self._window._parallelism,
            min=1,
            max=8,
        )
        if not ok:
            return
        self._window._parallelism = value
        showed_warning = (
            value > 1 and value > previous_value and not self._window._parallelism_warning_shown
        )
        if showed_warning:
            self._window._parallelism_warning_shown = True
        self.save_app_settings()
        self.update_parallelism_labels()
        if showed_warning:
            self._window._notify(
                "Parallel Processing Risk",
                "Chunk parallelism was increased above 1. Higher values can trigger rate limits, "
                "may slow down jobs through retries, and are often best kept at 2 or 3 unless your "
                "account stays stable.",
                level="warning",
            )
            return
        self._window._notify("Parallelism Updated", f"Chunk parallelism set to {value}.")

    def schedule_counts_update(self) -> None:
        self._window._count_timer.start()

    def update_counts(self) -> None:
        text = self._window.text_edit.toPlainText()
        chars = len(text)
        chunks = split_text(text, config.MAX_CHUNK_SIZE) if text else []
        self._window.char_count_label.setText(f"Character Count: {chars}")
        self._window.chunk_count_label.setText(f"Chunks: {len(chunks)}")
        self._window.price_estimate_label.setText(self.format_price_estimate(chars))
        self.update_parallelism_labels()

    def format_price_estimate(self, chars: int) -> str:
        model = self._window.model_combo.currentText()
        price_per_1m = config.TTS_CHARACTER_PRICE_USD_PER_1M.get(model)
        if price_per_1m is not None:
            return f"Estimated price: {self.format_usd(self.character_price(chars, price_per_1m))}"
        if model == config.GPT_4O_MINI_TTS_MODEL:
            return f"Estimated price: ~{self.format_usd(self.gpt_4o_mini_tts_estimate(chars))}"
        return "Estimated price: unavailable"

    def character_price(self, chars: int, price_per_1m: float) -> Decimal:
        return Decimal(chars) * Decimal(str(price_per_1m)) / Decimal("1000000")

    def gpt_4o_mini_tts_estimate(self, chars: int) -> Decimal:
        text_tokens = Decimal(chars) / Decimal(
            str(config.GPT_4O_MINI_TTS_ESTIMATED_CHARS_PER_TEXT_TOKEN)
        )
        input_cost = (
            text_tokens
            * Decimal(str(config.GPT_4O_MINI_TTS_TEXT_INPUT_USD_PER_1M_TOKENS))
            / Decimal("1000000")
        )
        audio_minutes = Decimal(chars) / Decimal(
            str(config.GPT_4O_MINI_TTS_ESTIMATED_CHARS_PER_AUDIO_MINUTE)
        )
        output_cost = audio_minutes * Decimal(
            str(config.GPT_4O_MINI_TTS_ESTIMATED_AUDIO_OUTPUT_USD_PER_MINUTE)
        )
        return input_cost + output_cost

    def format_usd(self, value: Decimal) -> str:
        return f"${value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"

    def update_instructions_enabled(self) -> None:
        is_gpt4o_mini = self._window.model_combo.currentText() == config.GPT_4O_MINI_TTS_MODEL
        self._window.instructions_edit.setEnabled(
            is_gpt4o_mini and self._window.create_button.isEnabled()
        )
        self._window.instructions_label.setEnabled(is_gpt4o_mini)
        self._window.manage_presets_button.setEnabled(
            is_gpt4o_mini and self._window.create_button.isEnabled()
        )

    def update_path_extension(self, selected_format: str) -> None:
        current_path = self._window.path_entry.text()
        if not current_path:
            return
        self._window.path_entry.setText(self.normalize_output_path(current_path, selected_format))
        self._window._refresh_request_ids_button()

    def default_output_path(self, selected_format: str) -> str:
        os.makedirs(config.DEFAULT_OUTPUT_DIR, exist_ok=True)
        extension = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        candidate = Path(config.DEFAULT_OUTPUT_DIR) / f"output{extension}"
        if not candidate.exists():
            return str(candidate)
        for index in range(1, 10_000):
            candidate = Path(config.DEFAULT_OUTPUT_DIR) / f"output-{index}{extension}"
            if not candidate.exists():
                return str(candidate)
        return str(Path(config.DEFAULT_OUTPUT_DIR) / f"output-{os.getpid()}{extension}")

    def normalize_output_path(self, current_path: str, selected_format: str) -> str:
        path = current_path.strip()
        if not path:
            return self.default_output_path(selected_format)
        normalized = Path(path)
        required_extension = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        if normalized.suffix.lower() != required_extension.lower():
            normalized = normalized.with_suffix(required_extension)
        return str(normalized)

    def select_save_path(self) -> None:
        selected_format = self._window.format_combo.currentText()
        file_filter = config.FORMAT_FILTER_MAP.get(selected_format, config.FORMAT_FILTER_MAP["all"])
        current_path = self._window.path_entry.text()
        start_dir = os.path.dirname(current_path) if current_path else config.DEFAULT_OUTPUT_DIR
        os.makedirs(start_dir, exist_ok=True)
        extension = config.FORMAT_EXTENSION_MAP.get(selected_format, ".mp3")
        start_path = current_path or os.path.join(start_dir, f"output{extension}")
        file_path, _ = QFileDialog.getSaveFileName(
            self._window, "Save TTS Audio As", start_path, file_filter
        )
        if not file_path:
            return
        self._window.path_entry.setText(self.normalize_output_path(file_path, selected_format))
        self._window._refresh_request_ids_button()

    def set_custom_api_key(self) -> None:
        from ..keystore import save_api_key

        current = self._window._api_key or ""
        api_key, ok = QInputDialog.getText(
            self._window,
            "Set OpenAI API Key",
            "Enter your OpenAI API key (stored in keyring when available):",
            QLineEdit.EchoMode.Password,
            current,
        )
        if not ok:
            return
        api_key = api_key.strip()
        if not api_key:
            self._window._notify("Empty Key", "API key cannot be empty.", level="warning")
            return
        if save_api_key(api_key):
            self._window._api_key = api_key
            self._window._notify("API Key Set", "API key saved.")
            return
        self._window._notify("Error", "Failed to save API key.", level="critical")

    def check_api_key_on_startup(self) -> None:
        if self._window._api_key or self._window._startup_api_key_notice_shown:
            return
        self._window._startup_api_key_notice_shown = True
        self._window._notify(
            "API Key Missing",
            "No OpenAI API key found. Set one in the 'API Key' menu.",
            level="warning",
        )

    def load_api_key_from_file(self) -> None:
        self._window._start_api_key_load(notify_on_result=True)

    def open_preset_dialog(self) -> None:
        from .dialogs import PresetDialog

        dialog = PresetDialog(self._window.instructions_edit.toPlainText(), self._window)
        dialog.preset_selected.connect(self.apply_preset)
        dialog.exec()

    def apply_preset(self, instructions: str) -> None:
        self._window.instructions_edit.setPlainText(instructions)
