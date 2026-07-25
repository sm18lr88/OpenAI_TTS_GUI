from __future__ import annotations

from openai_tts_gui.tts import CancellationStage, RunState
from openai_tts_gui.tts._run_state import AttemptKey


class _Response:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_run_state_selects_awaiting_before_stream_and_closes_registered_response() -> None:
    # Given: one call awaiting provider headers and a later call with a live stream.
    state = RunState(planned_chunks=2, cancel_event=None)
    awaiting = AttemptKey(1, 1)
    streaming = AttemptKey(2, 1)
    response = _Response()
    assert state.begin_attempt(awaiting)
    assert state.begin_attempt(streaming)
    assert state.register_response(streaming, response)

    # When: external cancellation races with both resource types.
    stage = state.request_cancel()

    # Then: the immutable stage records the higher-priority uninterruptible call once.
    assert stage is CancellationStage.AWAITING_PROVIDER_RESPONSE
    assert response.closed == 1
    state.complete_attempt(awaiting)
    state.complete_attempt(streaming)
    assert state.freeze().cancellation_stage is CancellationStage.AWAITING_PROVIDER_RESPONSE
