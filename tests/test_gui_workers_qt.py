from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from openai_tts_gui.gui import workers as worker_module
from openai_tts_gui.gui.workers import ApiKeyLoadWorker, TTSWorker, WorkerParameters
from openai_tts_gui.keystore import KeyringCredential
from openai_tts_gui.tts import (
    CancellationStage,
    ChunkCompleted,
    GenerationHooks,
    ProviderFailureOutcome,
    RunAccounting,
    RunStarted,
    SuccessOutcome,
)


class _UnexpectedWorkerError(Exception):
    pass


def _worker_params() -> WorkerParameters:
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
    captured = {}

    class FakeTTSService:
        def __init__(self, **kwargs) -> None:
            captured["init"] = kwargs

        def execute(self, request, hooks: GenerationHooks) -> SuccessOutcome:
            captured["request"] = request
            hooks.on_progress(RunStarted(1))
            hooks.on_progress(ChunkCompleted(1, None))
            hooks.on_status("Generating chunk 1")
            hooks.on_parallelism(1, 2)
            accounting = RunAccounting(1, 1, 1, 1, (), (), CancellationStage.NONE)
            return SuccessOutcome("TTS complete", request.output_path, accounting)

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
    assert captured["request"].config.parallelism == 2
    assert progress == [1, 95]
    assert statuses == ["Generating chunk 1"]
    assert parallelism == [(1, 2)]
    assert complete == ["TTS complete"]
    assert errors == []


@pytest.mark.parametrize(
    ("exception", "expected_message"),
    [
        ("service failed", "service failed"),
    ],
)
def test_tts_worker_errors_emit_error_signal(monkeypatch, exception, expected_message):
    class FakeTTSService:
        def __init__(self, **_kwargs) -> None:
            pass

        def execute(self, request, hooks: GenerationHooks) -> ProviderFailureOutcome:
            accounting = RunAccounting(0, 0, 0, 0, (), (), CancellationStage.NONE)
            return ProviderFailureOutcome(exception, accounting)

    monkeypatch.setattr(worker_module, "TTSService", FakeTTSService)
    worker = TTSWorker(_worker_params())

    complete: list[str] = []
    errors: list[str] = []

    worker.tts_complete.connect(complete.append)
    worker.tts_error.connect(errors.append)

    worker.run()

    assert complete == []
    assert errors == [expected_message]


def test_tts_worker_surfaces_unexpected_programmer_errors(monkeypatch) -> None:
    class FakeTTSService:
        def __init__(self, **_kwargs) -> None:
            pass

        def execute(self, *_args):
            raise _UnexpectedWorkerError("unexpected failure")

    monkeypatch.setattr(worker_module, "TTSService", FakeTTSService)

    with pytest.raises(_UnexpectedWorkerError, match="unexpected failure"):
        TTSWorker(_worker_params()).run()


def test_tts_worker_cancel_suppresses_progress_signal():
    worker = TTSWorker(_worker_params())
    progress: list[int] = []
    worker.progress_updated.connect(progress.append)

    worker._emit_progress(RunStarted(1))
    worker.cancel()
    worker._emit_progress(ChunkCompleted(1, None))

    assert worker._cancel_event.is_set() is True
    assert progress == [1]


def test_api_key_load_worker_emits_stored_key(monkeypatch):
    monkeypatch.setattr(
        "openai_tts_gui.keystore.read_api_key_outcome",
        lambda: KeyringCredential("sk-worker-test"),
    )
    worker = ApiKeyLoadWorker()

    loaded = []
    worker.api_key_loaded.connect(loaded.append)

    worker.run()

    assert loaded == ["sk-worker-test"]
