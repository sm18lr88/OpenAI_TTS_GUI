from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("PyQt6")

from openai_tts_gui.errors import TTSAPIError
from openai_tts_gui.gui import workers as worker_module
from openai_tts_gui.gui.workers import ApiKeyLoadWorker, TTSWorker


def _worker_params() -> dict[str, Any]:
    return {
        "api_key": "test-key",
        "text": "Hello from the worker",
        "output_path": "out.mp3",
        "model": "tts-1",
        "voice": "alloy",
        "response_format": "mp3",
        "speed": 1.0,
        "instructions": "",
        "parallelism": 2,
        "retain_files": False,
    }


def test_tts_worker_success_forwards_service_callbacks(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeTTSService:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def generate(self, **kwargs: Any) -> str:
            captured["generate"] = kwargs
            kwargs["on_progress"](42)
            kwargs["on_status"]("Generating chunk 1")
            kwargs["on_parallelism"](1, 2)
            return "TTS complete"

    monkeypatch.setattr(worker_module, "TTSService", FakeTTSService)
    worker = TTSWorker(_worker_params())

    progress: list[int] = []
    statuses: list[str] = []
    parallelism: list[tuple[int, int]] = []
    complete: list[str] = []
    errors: list[str] = []

    worker.progress_updated.connect(progress.append)
    worker.status_update.connect(statuses.append)
    worker.parallelism_updated.connect(lambda active, cap: parallelism.append((active, cap)))
    worker.tts_complete.connect(complete.append)
    worker.tts_error.connect(errors.append)

    worker.run()

    assert captured["init"]["api_key"] == "test-key"
    assert captured["generate"]["cancel_event"].is_set() is False
    assert captured["generate"]["parallelism"] == 2
    assert progress == [42]
    assert statuses == ["Generating chunk 1"]
    assert parallelism == [(1, 2)]
    assert complete == ["TTS complete"]
    assert errors == []


@pytest.mark.parametrize(
    ("exception", "expected_message"),
    [
        (TTSAPIError("service failed"), "service failed"),
        (RuntimeError("unexpected failure"), "unexpected failure"),
    ],
)
def test_tts_worker_errors_emit_error_signal(monkeypatch, exception, expected_message):
    class FakeTTSService:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def generate(self, **_kwargs: Any) -> str:
            raise exception

    monkeypatch.setattr(worker_module, "TTSService", FakeTTSService)
    worker = TTSWorker(_worker_params())

    complete: list[str] = []
    errors: list[str] = []

    worker.tts_complete.connect(complete.append)
    worker.tts_error.connect(errors.append)

    worker.run()

    assert complete == []
    assert errors == [expected_message]


def test_tts_worker_cancel_suppresses_progress_signal():
    worker = TTSWorker(_worker_params())
    progress: list[int] = []
    worker.progress_updated.connect(progress.append)

    worker._emit_progress(10)
    worker.cancel()
    worker._emit_progress(90)

    assert worker._cancel_event.is_set() is True
    assert progress == [10]


def test_api_key_load_worker_emits_stored_key(monkeypatch):
    monkeypatch.setattr("openai_tts_gui.keystore.read_api_key", lambda: "sk-worker-test")
    worker = ApiKeyLoadWorker()

    loaded: list[object] = []
    worker.api_key_loaded.connect(loaded.append)

    worker.run()

    assert loaded == ["sk-worker-test"]
