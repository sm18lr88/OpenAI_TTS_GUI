from __future__ import annotations

import threading
from pathlib import Path

import pytest

from openai_tts_gui.errors import ContractError, TTSCancelledError, TTSChunkError
from openai_tts_gui.tts import RunState
from openai_tts_gui.tts._publication import ChunkRequestMeta, ChunkTask
from openai_tts_gui.tts._run_state import AttemptKey
from openai_tts_gui.tts._scheduler import (
    RunCoordinator,
    ScheduledBatch,
    ensure_not_cancelled,
    generate_parallel,
    generate_serial,
    record_metadata,
)


def _batch(
    task: ChunkTask,
    *,
    state: RunState | None = None,
    on_between_chunks=None,
) -> ScheduledBatch:
    return ScheduledBatch(
        (task,),
        {},
        {task.index},
        threading.Lock(),
        None,
        None,
        None,
        None if state is None else state.cancel_event,
        on_between_chunks=on_between_chunks,
        state=state,
    )


def test_serial_scheduler_reports_the_between_chunks_boundary(tmp_path: Path) -> None:
    task = ChunkTask(1, "speech", tmp_path / "chunk.wav")
    boundaries: list[str] = []
    batch = _batch(task, on_between_chunks=lambda: boundaries.append("between"))

    generate_serial(
        batch,
        lambda *, task: ChunkRequestMeta(1, "request-1", None, str(task.filename), 1, 6),
    )

    assert boundaries == ["between"]


def test_parallel_scheduler_stops_reserving_after_run_cancellation(tmp_path: Path) -> None:
    state = RunState(1, None)
    state.request_cancel()
    task = ChunkTask(1, "speech", tmp_path / "chunk.wav")

    generate_parallel(
        _batch(task, state=state),
        lambda *, task: pytest.fail(f"cancelled task ran: {task.index}"),
        RunCoordinator(1),
        None,
    )


def test_parallel_scheduler_cancels_work_when_attachment_loses_admission(tmp_path: Path) -> None:
    class CancelOnAttachState(RunState):
        def attach(self, index: int, cancel) -> bool:
            super().attach(index, cancel)
            self.request_cancel()
            return False

    state = CancelOnAttachState(1, None)
    task = ChunkTask(1, "speech", tmp_path / "chunk.wav")

    with pytest.raises(TTSCancelledError):
        generate_parallel(
            _batch(task, state=state),
            lambda *, task: ChunkRequestMeta(
                task.index, "request-1", None, str(task.filename), 1, len(task.text)
            ),
            RunCoordinator(1),
            None,
        )


def test_scheduler_rejects_set_cancellation_event() -> None:
    event = threading.Event()
    event.set()

    with pytest.raises(TTSCancelledError):
        ensure_not_cancelled(event)


def test_scheduler_rejects_unexpected_result_index(tmp_path: Path) -> None:
    metadata: dict[int, ChunkRequestMeta] = {}
    result = ChunkRequestMeta(2, None, None, str(tmp_path / "chunk.wav"), 1, 6)

    with pytest.raises(TTSChunkError, match="Unexpected chunk result index"):
        record_metadata(
            meta=result,
            chunk_meta=metadata,
            expected_indexes={1},
            meta_lock=threading.Lock(),
        )


def test_run_state_rejects_acceptance_without_validated_ownership() -> None:
    state = RunState(1, None)

    with pytest.raises(ContractError, match="validated provider ownership"):
        state.accept_validated_result(AttemptKey(1, 1), None)


def test_run_state_reconciles_legacy_completion_and_request_id() -> None:
    state = RunState(1, None)
    state.reconcile_completed_attempt(1, 2)
    key = AttemptKey(1, 2)
    state._validated_results.add(key)

    state.accept_validated_result(key, "request-1")
    accounting = state.freeze()

    assert accounting.client_attempts_started == 2
    assert accounting.completed_indexes == (1,)
    assert accounting.request_ids == ("request-1",)


def test_run_state_rejects_completion_without_a_started_attempt() -> None:
    state = RunState(1, None)
    key = AttemptKey(1, 1)
    state._validated_results.add(key)

    with pytest.raises(ContractError, match="recorded started attempt"):
        state.accept_validated_result(key, None)
