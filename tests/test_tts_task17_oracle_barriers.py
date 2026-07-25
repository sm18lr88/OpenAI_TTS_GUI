from __future__ import annotations

import time

import pytest

from openai_tts_gui.errors import ContractError
from openai_tts_gui.tts import CancellationStage, PublicationInProgress, RunState
from openai_tts_gui.tts._run_state import AttemptKey


class _Response:
    def close(self) -> None:
        return None


def test_run_state_rejects_future_attachment_without_a_reservation() -> None:
    # Given: a run with no queued scheduler reservation.
    state = RunState(1, None)

    # When / Then: attaching a cancellation owner cannot fabricate queued work.
    with pytest.raises(ContractError, match="reserved"):
        state.attach(1, lambda: True)


def test_retry_transition_retains_owner_until_retry_wait_is_registered() -> None:
    # Given: a provider attempt that received a definitive retryable response.
    state = RunState(1, None)
    key = AttemptKey(1, 1)
    assert state.begin_attempt(key)
    assert state.register_response(key, _Response())

    # When: one atomic transition exchanges the response owner for retry-wait ownership.
    state.transition_attempt_to_retry_wait(key)

    # Then: cancellation sees retry waiting, never an unowned before-request gap.
    assert state.request_cancel() is CancellationStage.DURING_RETRY_WAIT
    state.finish_retry_wait(key)
    assert state.freeze().cancellation_stage is CancellationStage.DURING_RETRY_WAIT


def test_publication_is_an_owner_and_freeze_rejects_unfinished_publication() -> None:
    # Given: publication has won the atomic cancellation gate.
    state = RunState(1, None)
    assert isinstance(state.begin_publication(), PublicationInProgress)

    # When / Then: terminal accounting cannot freeze while publication still owns the run.
    with pytest.raises(ContractError, match="publication"):
        state.freeze()
    state.finish_publication()
    assert state.freeze().cancellation_stage is CancellationStage.NONE


def test_request_stop_returns_without_waiting_for_escalation(monkeypatch) -> None:
    # Given: a stopper whose graceful signal is accepted but process remains unreaped.
    from openai_tts_gui.core import _ffmpeg_process as process_module
    from openai_tts_gui.core._ffmpeg_process import FfmpegProcess

    class _RunningProcess:
        pid = 41

        def poll(self) -> None:
            return None

    process = FfmpegProcess(["ffmpeg"])
    monkeypatch.setattr(process, "_process", _RunningProcess())
    monkeypatch.setattr(process_module.os, "name", "nt")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        process_module.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )

    # When: the GUI-facing cancellation action requests a stop.
    started = time.monotonic()
    process.request_stop()

    # Then: it only sends the graceful signal and leaves reaping to the owner.
    assert time.monotonic() - started < 0.1
    assert calls == [["taskkill", "/PID", "41", "/T"]]
