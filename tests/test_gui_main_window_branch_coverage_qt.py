from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol

import pytest
from PyQt6.QtCore import Qt

from openai_tts_gui import config
from openai_tts_gui.gui import TTSWindow
from openai_tts_gui.gui import _result_actions as result_actions_module
from openai_tts_gui.gui import workers as worker_module
from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    GenerationHooks,
    RunAccounting,
    SuccessOutcome,
)


def _window(qtbot) -> TTSWindow:
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    return window


def _notifications(window: TTSWindow) -> list[tuple[str, str, str]]:
    notices: list[tuple[str, str, str]] = []

    def record(title: str, message: str, level: str = "info", **_kwargs: bool) -> None:
        notices.append((title, message, level))

    window._notify = record
    return notices


class ClipboardSink(Protocol):
    def setText(self, text: str) -> None: ...


class RecordingClipboard:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


def test_start_creation_validates_key_text_path_and_speed_via_controls(
    qtbot, tmp_path, monkeypatch
) -> None:
    window = _window(qtbot)
    notices = _notifications(window)

    qtbot.mouseClick(window.create_button, Qt.MouseButton.LeftButton)
    window._api_key = "key"
    qtbot.mouseClick(window.create_button, Qt.MouseButton.LeftButton)

    window.text_edit.setPlainText("A real request")
    directory_path = tmp_path / "directory-output.mp3"
    directory_path.mkdir()
    window.path_entry.setText(str(directory_path))
    qtbot.mouseClick(window.create_button, Qt.MouseButton.LeftButton)

    window.path_entry.setText(str(tmp_path / "audio.mp3"))
    window.speed_input.setText("0")

    class SuccessfulService:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: float) -> None:
            pass

        def execute(
            self,
            request,
            _hooks: GenerationHooks,
        ) -> SuccessOutcome:
            return SuccessOutcome(
                "created",
                request.output_path,
                RunAccounting(1, 1, 1, 1, (), (), CancellationStage.NONE),
            )

    monkeypatch.setattr(worker_module, "TTSService", SuccessfulService)
    qtbot.mouseClick(window.create_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.tts_processor is None, timeout=2_000)

    assert notices[:4] == [
        ("API Key Missing", "Set your OpenAI API key in the 'API Key' menu.", "warning"),
        ("Empty Text", "Please enter some text.", "warning"),
        ("Path Error", "Output path points to a directory.", "critical"),
        (
            "Invalid Speed",
            f"Speed must be between {config.MIN_SPEED} and {config.MAX_SPEED}. "
            f"Using {config.DEFAULT_SPEED}.",
            "warning",
        ),
    ]
    assert window.speed_input.text() == str(config.DEFAULT_SPEED)
    assert window.create_button.isEnabled()
    assert not window.cancel_button.isEnabled()


def test_creation_cancel_and_error_restore_controls_with_real_thread(
    qtbot, tmp_path, monkeypatch
) -> None:
    entered = threading.Event()
    window = _window(qtbot)
    notices = _notifications(window)
    window._api_key = "key"
    window.text_edit.setPlainText("Cancel me")
    window.path_entry.setText(str(tmp_path / "cancel.mp3"))

    class BlockingService:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: float) -> None:
            pass

        def request_cancel(self) -> CancellationStage:
            return CancellationStage.NONE

        def execute(
            self,
            _request,
            hooks: GenerationHooks,
        ) -> CancelledOutcome:
            entered.set()
            assert hooks.cancel_event is not None and hooks.cancel_event.wait(1)
            return CancelledOutcome(
                "request cancelled",
                RunAccounting(1, 1, 0, 0, (), (), CancellationStage.BEFORE_REQUEST),
            )

    monkeypatch.setattr(worker_module, "TTSService", BlockingService)
    qtbot.mouseClick(window.create_button, Qt.MouseButton.LeftButton)
    assert entered.wait(1)
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.tts_processor is None, timeout=2_000)

    assert window.create_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert notices[-1] == ("TTS Cancelled", "request cancelled", "warning")


def test_sidecar_request_ids_and_parallelism_outcomes_are_visible(
    qtbot, tmp_path, monkeypatch
) -> None:
    window = _window(qtbot)
    notices = _notifications(window)
    output = tmp_path / "audio.mp3"
    sidecar = Path(f"{output}.json")
    clipboard = RecordingClipboard()
    clipboard_boundary: ClipboardSink = clipboard
    monkeypatch.setattr(result_actions_module.QApplication, "clipboard", lambda: clipboard_boundary)

    window.path_entry.setText(str(output))
    window._refresh_request_ids_button()
    assert not window.copy_ids_button.isEnabled()

    sidecar.write_text("not json", encoding="utf-8")
    window._refresh_request_ids_button()
    assert not window.copy_ids_button.isEnabled()

    sidecar.write_text(
        json.dumps(
            {
                "parallelism_used": 2,
                "request_meta": [
                    {"request_id": "request-one"},
                    {"request_id": "request-one"},
                    {"request_id": "request-two"},
                    {},
                ],
            }
        ),
        encoding="utf-8",
    )
    window._refresh_request_ids_button()
    qtbot.mouseClick(window.copy_ids_button, Qt.MouseButton.LeftButton)
    window._handle_tts_success("done")

    assert window.copy_ids_button.isEnabled()
    assert clipboard.text == "request-one\nrequest-two"
    assert window.parallelism_status_label.text() == "Last run parallelism used: 2"
    assert notices[-2:] == [
        ("Copied", "Request IDs copied to clipboard.", "info"),
        (
            "TTS Complete",
            'done\n\nShow <a href="https://paypal.me/LeoRiera">appreciation</a>.',
            "info",
        ),
    ]


def test_api_key_dialog_and_about_actions_update_accessible_controls(qtbot, monkeypatch) -> None:
    window = _window(qtbot)
    notices = _notifications(window)
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getText", lambda *_args: ("", True)
    )
    window._set_custom_api_key()
    monkeypatch.setattr(
        "openai_tts_gui.gui._window_settings.QInputDialog.getText", lambda *_args: ("new-key", True)
    )
    monkeypatch.setattr("openai_tts_gui.keystore.save_api_key", lambda _key: True)
    window._set_custom_api_key()

    window._show_about_page()
    qtbot.mouseClick(window.about_back_button, Qt.MouseButton.LeftButton)

    assert notices == [
        ("Empty Key", "API key cannot be empty.", "warning"),
        ("API Key Set", "API key saved.", "info"),
    ]
    assert window._api_key == "new-key"
    assert window.stack.currentIndex() == 0


def test_close_idle_window_accepts_without_confirmation(qtbot, monkeypatch) -> None:
    window = _window(qtbot)
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *_args: pytest.fail("idle close should not prompt"),
    )

    window.close()

    assert not window.isVisible()
