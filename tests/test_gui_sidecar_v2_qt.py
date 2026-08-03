from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from openai_tts_gui.core import (
    SidecarRequestInput,
    SidecarWriteInput,
    build_sidecar_v2,
    write_sidecar_metadata,
)
from openai_tts_gui.gui import TTSWindow
from openai_tts_gui.gui import _result_actions as result_actions_module


class RecordingClipboard:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


def test_v2_sidecar_request_ids_and_malformed_schema_are_safe_in_result_actions(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a v2 sidecar with a request ID and a clipboard boundary.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    notices: list[tuple[str, str, str]] = []
    window._notify = lambda title, message, level="info", **_kwargs: notices.append(
        (title, message, level)
    )
    output = tmp_path / "audio.wav"
    output.write_bytes(b"audio")
    clipboard = RecordingClipboard()
    monkeypatch.setattr(result_actions_module.QApplication, "clipboard", lambda: clipboard)
    sidecar = build_sidecar_v2(
        SidecarWriteInput(
            output,
            "tts-1",
            "alloy",
            "wav",
            1.0,
            1,
            4096,
            1,
            1,
            "audio",
            False,
            5,
            {"app_version": "test"},
            None,
            (SidecarRequestInput(1, "v2-request", "tts-1", "chunk_0001.wav", 1, 5, None),),
        )
    )
    write_sidecar_metadata(str(output), sidecar)
    window.path_entry.setText(str(output))

    # When: result actions copy the v2 request ID then encounter an unknown schema.
    window._refresh_request_ids_button()
    window._copy_request_ids()
    Path(f"{output}.json").write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    window._refresh_request_ids_button()
    window._copy_request_ids()

    # Then: valid v2 data works, and bad metadata shows a visible copy error.
    assert clipboard.text == "v2-request"
    assert not window.copy_ids_button.isEnabled()
    assert [notice[0] for notice in notices] == ["Copied", "Copy Failed"]


def test_result_actions_handle_empty_output_and_unavailable_clipboard(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = TTSWindow()
    qtbot.addWidget(window)
    notices: list[tuple[str, str, str]] = []
    window._notify = lambda title, message, level="info", **_kwargs: notices.append(
        (title, message, level)
    )

    assert window._read_parallelism_used() is None
    output = tmp_path / "audio.wav"
    Path(f"{output}.json").write_text(
        json.dumps({"parallelism_used": 2, "request_meta": [{"request_id": "req-v1"}]}),
        encoding="utf-8",
    )
    window.path_entry.setText(str(output))
    monkeypatch.setattr(result_actions_module.QApplication, "clipboard", lambda: None)

    assert window._read_parallelism_used() == 2
    window._copy_request_ids()

    assert notices == [("Copy Failed", "The clipboard is unavailable.", "warning")]
