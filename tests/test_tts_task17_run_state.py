from __future__ import annotations

import threading

import pytest

from openai_tts_gui.errors import ContractError
from openai_tts_gui.tts import CancellationStage, PublicationInProgress, RunState
from openai_tts_gui.tts._run_state import AttemptKey, RunPhase


class _QueuedCancelError(RuntimeError):
    pass


class _Response:
    def __init__(self, error: OSError | RuntimeError | None = None) -> None:
        self.close_calls = 0
        self._error = error

    def close(self) -> None:
        self.close_calls += 1
        if self._error is not None:
            raise self._error


class _Stopper:
    def __init__(self, error: OSError | RuntimeError | None = None) -> None:
        self.stop_calls = 0
        self._error = error

    def request_stop(self) -> None:
        self.stop_calls += 1
        if self._error is not None:
            raise self._error


def test_run_state_prioritizes_awaiting_headers_over_stream_and_late_attachment() -> None:
    # Given: a reserved future, an unreserved late attachment, and two provider owners.
    state = RunState(2, None)
    awaiting = AttemptKey(1, 1)
    streaming = AttemptKey(2, 1)
    response = _Response()
    assert state.phase is RunPhase.RUNNING
    assert state.cleanup_warnings == ()
    assert state.reserve(3)
    with pytest.raises(ContractError, match="reserved"):
        state.attach(99, lambda: True)
    assert state.begin_attempt(awaiting)
    assert state.begin_attempt(streaming)
    assert state.register_response(streaming, response)

    # When: cancellation observes both awaiting headers and an active response stream.
    stage = state.request_cancel()

    # Then: awaiting headers win and only the registered response closes.
    assert stage is CancellationStage.AWAITING_PROVIDER_RESPONSE
    assert response.close_calls == 1
    assert state.reserve(4) is False
    assert state.attach(3, lambda: True) is False
    assert state.admit(3) is False
    assert state.begin_attempt(AttemptKey(3, 1)) is False
    state.complete_attempt(awaiting)
    state.complete_attempt(streaming)
    state.discard_queued(3)
    assert state.freeze().cancellation_stage is CancellationStage.AWAITING_PROVIDER_RESPONSE


def test_run_state_closes_stream_once_and_keeps_terminal_waiting_for_owner_exit() -> None:
    # Given: an accepted stream owned by a run that has not exited its response context.
    state = RunState(1, None)
    key = AttemptKey(1, 1)
    response = _Response()
    frozen: list[CancellationStage] = []
    terminal = threading.Event()
    assert state.begin_attempt(key)
    assert state.register_response(key, response)

    def freeze_run() -> None:
        frozen.append(state.freeze().cancellation_stage)
        terminal.set()

    worker = threading.Thread(target=freeze_run)
    worker.start()
    assert not terminal.wait(0.05)

    # When: cancellation closes the response while its owner remains active.
    assert state.request_cancel() is CancellationStage.DURING_PROVIDER_STREAM
    assert state.request_cancel() is CancellationStage.DURING_PROVIDER_STREAM
    assert response.close_calls == 1
    assert not terminal.is_set()
    state.complete_attempt(key)

    # Then: terminal accounting arrives only after the owning response exits.
    assert terminal.wait(1.0)
    worker.join(timeout=1.0)
    assert frozen == [CancellationStage.DURING_PROVIDER_STREAM]


def test_run_state_records_cancel_action_cleanup_warnings_without_skipping_owners() -> None:
    # Given: each cancellable owner reports its documented cleanup failure.
    state = RunState(1, None)
    key = AttemptKey(1, 1)
    response = _Response(OSError("response locked"))
    stopper = _Stopper(RuntimeError("ffmpeg stuck"))

    def fail_queued_cancel() -> bool:
        state.discard_queued(1)
        raise _QueuedCancelError("future already running")

    assert state.reserve(1)
    assert state.attach(1, fail_queued_cancel)
    assert state.begin_attempt(key)
    assert state.register_response(key, response)
    assert state.begin_ffmpeg(stopper)

    # When: a stream-stage cancellation applies all independent cleanup actions.
    assert state.request_cancel() is CancellationStage.DURING_PROVIDER_STREAM

    # Then: all actions are attempted exactly once and their warnings remain auditable.
    assert response.close_calls == 1
    assert stopper.stop_calls == 1
    assert state.cleanup_warnings == (
        "Could not cancel the queued task: future already running",
        "Could not close the response: response locked",
        "Could not stop ffmpeg: ffmpeg stuck",
    )
    state.complete_attempt(key)
    state.finish_ffmpeg()
    assert state.freeze().cancellation_stage is CancellationStage.DURING_PROVIDER_STREAM


def test_run_state_covers_retry_ffmpeg_publication_and_ingress_boundaries() -> None:
    # Given: independent runs at the retry, ffmpeg, publication, and ingress boundaries.
    retry = RunState(1, None)
    retry_key = AttemptKey(1, 1)
    assert retry.begin_attempt(retry_key)
    retry.transition_attempt_to_retry_wait(retry_key)
    ffmpeg = RunState(1, None)
    stopper = _Stopper()
    assert ffmpeg.begin_ffmpeg(stopper)
    ingress = threading.Event()
    ingress.set()
    pre_cancelled = RunState(1, ingress)
    publishing = RunState(1, None)

    # When: cancellation reaches each distinct ownership boundary.
    assert retry.request_cancel() is CancellationStage.DURING_RETRY_WAIT
    assert ffmpeg.request_cancel() is CancellationStage.DURING_FFMPEG
    assert pre_cancelled.cancellation_requested()
    assert pre_cancelled.begin_publication() is CancellationStage.BEFORE_REQUEST
    assert isinstance(publishing.begin_publication(), PublicationInProgress)

    # Then: only publication rejects cancellation, while resource owners can complete and freeze.
    assert stopper.stop_calls == 1
    assert isinstance(publishing.request_cancel(), PublicationInProgress)
    retry.finish_retry_wait(retry_key)
    ffmpeg.finish_ffmpeg()
    assert retry.freeze().cancellation_stage is CancellationStage.DURING_RETRY_WAIT
    assert ffmpeg.freeze().cancellation_stage is CancellationStage.DURING_FFMPEG
    assert pre_cancelled.freeze().cancellation_stage is CancellationStage.BEFORE_REQUEST
    publishing.finish_publication()
    assert publishing.freeze().cancellation_stage is CancellationStage.NONE


def test_run_state_rejects_frozen_publication_and_nonempty_terminal_accounting() -> None:
    # Given: one completed run and one deliberately incomplete accounting snapshot.
    frozen = RunState(1, None)
    assert frozen.freeze().planned_chunks == 1
    incomplete = RunState(1, None)
    incomplete._in_flight.add(1)

    # When / Then: terminal lifecycle guards reject reuse and unresolved accounting.
    with pytest.raises(ContractError, match="A frozen run cannot start publication"):
        frozen.begin_publication()
    with pytest.raises(ContractError, match="already frozen"):
        frozen.freeze()
    with pytest.raises(ContractError, match="Final accounting requires no in-flight chunks"):
        incomplete.freeze()


def test_run_state_rejects_unowned_response_and_records_external_cancellation() -> None:
    state = RunState(1, None)
    key = AttemptKey(1, 1)

    with pytest.raises(ContractError, match="awaiting attempt"):
        state.register_response(key, _Response())

    assert state.begin_attempt(key)
    state.complete_attempt(key)
    state.record_request_id(None)
    state.record_request_id("  ")
    state.record_request_id("request-1")
    state.record_request_id("request-1")
    state.cancel_event.set()

    assert state.begin_publication() is CancellationStage.BEFORE_REQUEST
    accounting = state.freeze()
    assert accounting.request_ids == ("request-1",)
