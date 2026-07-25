from __future__ import annotations

import threading

import pytest
from PyQt6.QtCore import QThread

from openai_tts_gui.gui import workers as worker_module
from openai_tts_gui.gui.workers import (
    ApiKeyLoadWorker,
    FFmpegPreflightWorker,
    TTSWorker,
    WorkerParameters,
)
from openai_tts_gui.keystore import (
    KeyringCredential,
    MissingCredential,
    StaleLegacyCredentialWarning,
)
from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    ChunkCompleted,
    GenerationHooks,
    ProviderFailureOutcome,
    PublicationInProgress,
    RunAccounting,
    RunStarted,
    SuccessOutcome,
)


def _params() -> WorkerParameters:
    return {
        "api_key": "test-key",
        "text": "Hello from a real thread",
        "output_path": "out.mp3",
        "model": "tts-1",
        "voice": "alloy",
        "response_format": "mp3",
        "speed": 1.0,
        "instructions": "",
        "parallelism": 2,
        "retain_files": False,
    }


def _is_stopped(worker: QThread) -> bool:
    return worker.wait(100)


def test_tts_worker_forwards_success_and_callback_signals_from_qthread(qtbot, monkeypatch) -> None:
    class SuccessfulService:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: float) -> None:
            pass

        def execute(
            self,
            request,
            hooks: GenerationHooks,
        ) -> SuccessOutcome:
            hooks.on_progress(RunStarted(1))
            hooks.on_progress(ChunkCompleted(1, None))
            hooks.on_status("chunk 1")
            hooks.on_parallelism(1, 2)
            accounting = RunAccounting(1, 1, 1, 1, (), (), CancellationStage.NONE)
            return SuccessOutcome("saved", request.output_path, accounting)

    monkeypatch.setattr(worker_module, "TTSService", SuccessfulService)
    worker = TTSWorker(_params())
    progress: list[int] = []
    status: list[str] = []
    parallelism: list[tuple[int, int]] = []
    completed: list[str] = []
    worker.progress_updated.connect(progress.append)
    worker.status_update.connect(status.append)
    worker.parallelism_updated.connect(lambda active, cap: parallelism.append((active, cap)))
    worker.tts_complete.connect(completed.append)

    with qtbot.waitSignals([worker.tts_complete, worker.finished], timeout=2_000):
        worker.start()

    assert completed == ["saved"]
    assert progress == [1, 95]
    assert status == ["chunk 1"]
    assert parallelism == [(1, 2)]
    assert _is_stopped(worker)


def test_tts_worker_emits_domain_errors_from_qthread(qtbot, monkeypatch) -> None:
    class FailingService:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: float) -> None:
            pass

        def execute(
            self,
            _request,
            _hooks: GenerationHooks,
        ) -> ProviderFailureOutcome:
            accounting = RunAccounting(0, 0, 0, 0, (), (), CancellationStage.NONE)
            return ProviderFailureOutcome("domain failure", accounting)

    monkeypatch.setattr(worker_module, "TTSService", FailingService)
    worker = TTSWorker(_params())
    errors: list[str] = []
    worker.tts_error.connect(errors.append)
    with qtbot.waitSignals([worker.tts_error, worker.finished], timeout=2_000):
        worker.start()

    assert errors == ["domain failure"]
    assert _is_stopped(worker)


def test_tts_worker_cancel_suppresses_progress_and_emits_cancel_error(qtbot, monkeypatch) -> None:
    entered = threading.Event()

    class CancellableService:
        def __init__(self, *, api_key: str, base_url: str | None, timeout: float) -> None:
            pass

        def request_cancel(self) -> CancellationStage:
            return CancellationStage.NONE

        def execute(
            self,
            _request,
            hooks: GenerationHooks,
        ) -> CancelledOutcome:
            hooks.on_progress(RunStarted(1))
            entered.set()
            assert hooks.cancel_event is not None and hooks.cancel_event.wait(1)
            hooks.on_progress(ChunkCompleted(1, None))
            accounting = RunAccounting(1, 1, 0, 0, (), (), CancellationStage.BEFORE_REQUEST)
            return CancelledOutcome("cancelled", accounting)

    monkeypatch.setattr(worker_module, "TTSService", CancellableService)
    worker = TTSWorker(_params())
    progress: list[int] = []
    errors: list[str] = []
    worker.progress_updated.connect(progress.append)
    worker.tts_error.connect(errors.append)
    worker.start()
    assert entered.wait(1)
    with qtbot.waitSignals([worker.tts_error, worker.finished], timeout=2_000):
        worker.cancel()

    assert errors == ["cancelled"]
    assert progress == [1]
    assert worker._cancel_event.is_set()
    assert _is_stopped(worker)


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (
            PublicationInProgress(),
            "Publication is already in progress; waiting for verified finalization.",
        ),
        (
            CancellationStage.AWAITING_PROVIDER_RESPONSE,
            "Cancellation requested; waiting for the provider call to return.",
        ),
        (
            CancellationStage.DURING_PROVIDER_STREAM,
            "Cancellation requested; closing active response streams and waiting for workers.",
        ),
        (
            CancellationStage.DURING_FFMPEG,
            "Cancellation requested; stopping ffmpeg and cleaning staged files.",
        ),
        (CancellationStage.NONE, None),
        (CancellationStage.DURING_RETRY_WAIT, "Cancellation requested; queued work stopped."),
    ],
)
def test_tts_worker_maps_typed_cancellation_decisions_without_message_classification(
    decision: CancellationStage | PublicationInProgress, expected: str | None
) -> None:
    # Given: a typed cancellation decision from the run ownership boundary.
    worker = TTSWorker(_params())
    statuses: list[str] = []
    worker.status_update.connect(statuses.append)

    # When: the worker translates that decision for the status bar.
    worker._emit_cancel_status(decision)

    # Then: the selected message follows its typed stage rather than an error string.
    assert statuses == ([] if expected is None else [expected])


@pytest.mark.parametrize("outcome", [(True, "ready"), (False, "not available")])
def test_ffmpeg_preflight_worker_emits_real_preflight_outcome(qtbot, monkeypatch, outcome) -> None:
    monkeypatch.setattr("openai_tts_gui.core.ffmpeg.preflight_check", lambda: outcome)
    worker = FFmpegPreflightWorker()
    results: list[tuple[bool, str]] = []
    worker.preflight_finished.connect(lambda ok, detail: results.append((ok, detail)))
    with qtbot.waitSignals([worker.preflight_finished, worker.finished], timeout=2_000):
        worker.start()

    assert results == [outcome]
    assert _is_stopped(worker)


@pytest.mark.parametrize(
    ("outcome", "stored_key"),
    [(KeyringCredential("stored-key"), "stored-key"), (MissingCredential(), None)],
)
def test_api_key_loader_emits_keyring_outcome_from_qthread(
    qtbot, monkeypatch, outcome, stored_key
) -> None:
    monkeypatch.setattr("openai_tts_gui.keystore.read_api_key_outcome", lambda: outcome)
    worker = ApiKeyLoadWorker()
    results: list[str | None] = []
    worker.api_key_loaded.connect(results.append)
    with qtbot.waitSignals([worker.api_key_loaded, worker.finished], timeout=2_000):
        worker.start()

    assert results == [stored_key]
    assert _is_stopped(worker)


def test_api_key_loader_emits_stale_legacy_cleanup_guidance_once_from_qthread(
    qtbot, monkeypatch
) -> None:
    monkeypatch.setattr(
        "openai_tts_gui.keystore.read_api_key_outcome",
        lambda: KeyringCredential("stored-key", (StaleLegacyCredentialWarning(),)),
    )
    worker = ApiKeyLoadWorker()
    loaded: list[str | None] = []
    guidance: list[str] = []
    worker.api_key_loaded.connect(loaded.append)
    worker.legacy_credential_cleanup_required.connect(guidance.append)

    with qtbot.waitSignals(
        [worker.api_key_loaded, worker.legacy_credential_cleanup_required, worker.finished],
        timeout=2_000,
    ):
        worker.start()

    assert loaded == ["stored-key"]
    assert guidance == [StaleLegacyCredentialWarning().guidance]
    assert _is_stopped(worker)
