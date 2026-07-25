from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow


def _window(qtbot) -> TTSWindow:
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    return window


def _notices(window: TTSWindow) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []

    def record(title: str, message: str, level: str = "info", **_kwargs: bool) -> None:
        records.append((title, message, level))

    window._notify = record
    return records


def test_key_load_paths_set_notices_and_prevent_duplicate_startup_warning(qtbot) -> None:
    window = _window(qtbot)
    notices = _notices(window)

    window._api_key_load_notify = True
    window._handle_api_key_loaded("saved-key")
    window._handle_api_key_loaded(None)
    window._api_key_load_notify = False
    window._handle_api_key_loaded("")
    window._check_api_key_on_startup()

    assert notices == [
        ("API Key Reloaded", "API key loaded.", "info"),
        ("API Key Not Found", "No API key found.", "warning"),
        ("API Key Missing", "No OpenAI API key found. Set one in the 'API Key' menu.", "warning"),
    ]


def test_stale_legacy_cleanup_guidance_uses_status_and_single_structured_event(
    qtbot, caplog
) -> None:
    window = _window(qtbot)
    notices = _notices(window)

    with caplog.at_level(logging.WARNING, logger="openai_tts_gui.gui.main_window"):
        window._handle_legacy_credential_cleanup("Remove the legacy credential after verification.")

    cleanup_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "credential.legacy_cleanup_required"
    ]
    assert window.statusBar().currentMessage() == "Remove the legacy credential after verification."
    assert notices == []
    assert len(cleanup_records) == 1
    assert cleanup_records[0].outcome == "stale_legacy_credential"


def test_paths_parallelism_and_counts_cover_fallback_visible_states(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = _window(qtbot)
    notices = _notices(window)
    monkeypatch.setattr(config, "DEFAULT_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("openai_tts_gui.config.settings.DEFAULT_OUTPUT_DIR", str(tmp_path))
    existing = tmp_path / "output.mp3"
    existing.write_text("taken", encoding="utf-8")

    assert window._default_output_path("mp3").endswith("output-1.mp3")
    assert window._normalize_output_path("", "wav").endswith(".wav")
    window._update_path_extension("wav")
    window._update_progress_bar(37)
    window._update_parallelism_labels(last_used=3)
    window.model_combo.addItem("unsupported-model")
    window.model_combo.setCurrentText("unsupported-model")
    window.update_counts()

    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getInt",
        lambda *_args, **_kwargs: (1, False),
    )
    window._set_parallelism()

    assert window.progress_bar.value() == 37
    assert window.parallelism_status_label.text() == "Active chunk workers: idle"
    assert window.price_estimate_label.text() == "Estimated price: unavailable"
    assert notices == []


def test_notification_modes_and_api_key_failure_are_exposed(qtbot, monkeypatch) -> None:
    window = _window(qtbot)
    notices = _notices(window)
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getText", lambda *_args: ("key", True)
    )
    monkeypatch.setattr("openai_tts_gui.keystore.save_api_key", lambda _key: False)
    window._set_custom_api_key()

    window._notify = TTSWindow._notify.__get__(window, TTSWindow)
    window._dialogs_suppressed = lambda: False
    boxes: list[tuple[QMessageBox.Icon, Qt.TextFormat]] = []

    def record_exec(box: QMessageBox) -> QMessageBox.StandardButton:
        boxes.append((box.icon(), box.textFormat()))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr("openai_tts_gui.gui.main_window.QMessageBox.exec", record_exec)
    window._notify("Warning", "warn", level="warning")
    window._notify("Critical", "bad", level="critical")
    window._notify("Other", "other", level="other")

    assert notices == [("Error", "Failed to save API key.", "critical")]
    assert boxes == [
        (QMessageBox.Icon.Warning, Qt.TextFormat.PlainText),
        (QMessageBox.Icon.Critical, Qt.TextFormat.PlainText),
        (QMessageBox.Icon.Information, Qt.TextFormat.PlainText),
    ]


def test_request_id_empty_missing_and_read_error_notify_user(qtbot, tmp_path) -> None:
    window = _window(qtbot)
    notices = _notices(window)
    window._copy_request_ids()

    output = tmp_path / "missing.mp3"
    window.path_entry.setText(str(output))
    window._copy_request_ids()
    Path(f"{output}.json").write_text(json.dumps({"request_meta": [{}]}), encoding="utf-8")
    window._copy_request_ids()
    Path(f"{output}.json").write_text("broken", encoding="utf-8")
    window._copy_request_ids()

    assert [record[0] for record in notices] == [
        "No Output",
        "Sidecar Missing",
        "No Request IDs",
        "Copy Failed",
    ]


def test_request_id_invalid_sidecar_shapes_preserve_copy_failed(qtbot, tmp_path) -> None:
    # Given: a visible window and every JSON shape that cannot produce string request IDs.
    window = _window(qtbot)
    notices = _notices(window)
    output = tmp_path / "invalid.mp3"
    window.path_entry.setText(str(output))
    sidecar = Path(f"{output}.json")

    # When: request IDs are copied from each malformed-but-valid JSON payload.
    payloads = (
        [{"request_id": "id"}],
        "not-an-object",
        None,
        {"request_meta": {}},
        {"request_meta": [{"request_id": 42}]},
    )
    for payload in payloads:
        sidecar.write_text(json.dumps(payload), encoding="utf-8")
        window._copy_request_ids()

    # Then: every shape keeps the original visible copy failure outcome.
    assert [record[0] for record in notices] == ["Copy Failed"] * 5


def test_active_close_declines_confirmation_and_keeps_window_open(qtbot, monkeypatch) -> None:
    class ActiveWorker:
        def isRunning(self) -> bool:
            return True

    window = _window(qtbot)
    window.tts_processor = ActiveWorker()
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.No,
    )

    window.close()

    assert window.isVisible()
    window.tts_processor = None


def test_cancelled_api_dialog_and_running_generation_notify_without_mutating_state(
    qtbot, monkeypatch
) -> None:
    class RunningWorker:
        def isRunning(self) -> bool:
            return True

    window = _window(qtbot)
    notices = _notices(window)
    window._api_key = "existing"
    window.tts_processor = RunningWorker()
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getText",
        lambda *_args: ("changed", False),
    )

    window._set_custom_api_key()
    qtbot.mouseClick(window.create_button, Qt.MouseButton.LeftButton)
    window.tts_processor = None

    assert window._api_key == "existing"
    assert notices == [("Already Running", "A TTS generation is already in progress.", "warning")]


def test_save_cancel_preset_apply_error_status_and_folder_actions(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = _window(qtbot)
    notices = _notices(window)
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QFileDialog.getSaveFileName", lambda *_args: ("", "")
    )
    monkeypatch.setattr("openai_tts_gui.gui._result_actions.sys.platform", "darwin")
    opened: list[list[str]] = []
    monkeypatch.setattr("openai_tts_gui.gui._result_actions.subprocess.Popen", opened.append)

    window.select_save_path()
    window._apply_preset("calm and precise")
    window._handle_status_update("working")
    window._handle_tts_error("network rejected request")
    window._open_containing_folder(str(tmp_path / "audio.mp3"))

    assert window.instructions_edit.toPlainText() == "calm and precise"
    assert window.statusBar().currentMessage() == "working"
    assert notices[-1] == ("TTS Error", "network rejected request", "critical")
    assert opened == [["open", str(tmp_path)]]
