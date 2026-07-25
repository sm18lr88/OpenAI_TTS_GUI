from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QMessageBox

from openai_tts_gui.errors import CanonicalState, FinalizationReport, PublicationFailureReason
from openai_tts_gui.gui import TTSWindow
from openai_tts_gui.gui.workers import TTSWorker, WorkerParameters
from openai_tts_gui.tts import (
    CancellationStage,
    CancelledOutcome,
    CancelRequested,
    ChunkFailureOutcome,
    DestinationChangedOutcome,
    FfmpegFailureOutcome,
    FfmpegNotFoundOutcome,
    GenerationOutcome,
    OutputBusyOutcome,
    ProviderFailureOutcome,
    PublicationFailureOutcome,
    PublicationInProgress,
    PublicationRecoveryFailureOutcome,
    PublicationStarted,
    RunAccounting,
    UnknownFailureOutcome,
)


def _params() -> WorkerParameters:
    return {
        "api_key": "test-key",
        "text": "terminal outcome",
        "output_path": "out.mp3",
        "model": "tts-1",
        "voice": "alloy",
        "response_format": "mp3",
        "speed": 1.0,
    }


def _terminal_cases() -> tuple[tuple[GenerationOutcome, str, str, str], ...]:
    empty = RunAccounting(0, 0, 0, 0, (), (), CancellationStage.NONE)
    cancelled = RunAccounting(0, 0, 0, 0, (), (), CancellationStage.BEFORE_REQUEST)
    finalization = FinalizationReport(CanonicalState.ORIGINAL_DESTINATION)
    return (
        (CancelledOutcome("cancelled", cancelled), "cancelled", "TTS Cancelled", "warning"),
        (ProviderFailureOutcome("provider", empty), "provider", "TTS Error", "critical"),
        (ChunkFailureOutcome("chunk", 1, empty), "chunk", "TTS Error", "critical"),
        (FfmpegFailureOutcome("ffmpeg", empty), "ffmpeg", "TTS Error", "critical"),
        (FfmpegNotFoundOutcome("missing", empty), "missing", "TTS Error", "critical"),
        (
            PublicationRecoveryFailureOutcome(
                "recovery",
                PublicationFailureReason.RESTORE_SIDECAR,
                finalization,
                empty,
            ),
            "recovery",
            "TTS Error",
            "critical",
        ),
        (
            PublicationFailureOutcome(
                "publication",
                PublicationFailureReason.STAGE_AUDIO,
                finalization,
                empty,
            ),
            "publication",
            "TTS Error",
            "critical",
        ),
        (UnknownFailureOutcome("unknown", empty), "unknown", "TTS Error", "critical"),
        (
            OutputBusyOutcome("busy.mp3", empty),
            "Output is busy: busy.mp3",
            "TTS Error",
            "critical",
        ),
        (
            DestinationChangedOutcome("changed.mp3", "replaced", empty),
            "Output changed: changed.mp3 (replaced)",
            "TTS Error",
            "critical",
        ),
    )


@pytest.mark.parametrize(("outcome", "expected", "_title", "_level"), _terminal_cases())
def test_worker_routes_every_terminal_failure_to_error_signal(
    outcome: GenerationOutcome, expected: str, _title: str, _level: str
) -> None:
    worker = TTSWorker(_params())
    terminal: list[GenerationOutcome] = []
    errors: list[str] = []
    worker.terminal_outcome.connect(terminal.append)
    worker.tts_error.connect(errors.append)

    worker._emit_terminal(outcome)

    assert terminal == [outcome]
    assert errors == [expected]


@pytest.mark.parametrize(("outcome", "expected", "title", "level"), _terminal_cases())
def test_window_routes_every_terminal_failure_to_notification(
    qtbot, outcome: GenerationOutcome, expected: str, title: str, level: str
) -> None:
    window = TTSWindow()
    qtbot.addWidget(window)
    notices: list[tuple[str, str, str]] = []

    def notification(name: str, message: str, level: str = "info", **_kwargs: bool) -> None:
        notices.append((name, message, level))

    window._notify = notification

    window._run_wiring.handle_outcome(outcome)

    assert notices == [(title, expected, level)]
    assert window.create_button.isEnabled()
    assert not window.cancel_button.isEnabled()


@pytest.mark.parametrize(
    "decision",
    [PublicationInProgress(), CancellationStage.BETWEEN_CHUNKS],
)
def test_worker_cancel_handles_active_typed_decisions(
    decision: CancellationStage | PublicationInProgress,
) -> None:
    class ActiveService:
        def request_cancel(self) -> CancellationStage | PublicationInProgress:
            return decision

    worker = TTSWorker(_params())
    statuses: list[str] = []
    worker.status_update.connect(statuses.append)
    worker._service = ActiveService()

    worker.cancel()

    assert statuses
    assert not worker._cancel_event.is_set()


def test_worker_progress_routes_publication_and_ignores_nonvisual_events() -> None:
    worker = TTSWorker(_params())
    progress: list[int] = []
    worker.progress_updated.connect(progress.append)

    worker._emit_progress(PublicationStarted())
    worker._emit_progress(CancelRequested(CancellationStage.BEFORE_REQUEST))

    assert progress == [100]


def test_success_prompt_opens_output_folder_when_user_accepts(qtbot, monkeypatch) -> None:
    window = TTSWindow()
    qtbot.addWidget(window)
    opened: list[str] = []
    window.path_entry.setText("result.mp3")
    window._dialogs_suppressed = lambda: False
    window._notify = lambda *_args, **_kwargs: None
    window._open_containing_folder = opened.append
    monkeypatch.setattr(
        "openai_tts_gui.gui._run_wiring.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )

    window._run_wiring.handle_tts_success("saved")

    assert opened == ["result.mp3"]
