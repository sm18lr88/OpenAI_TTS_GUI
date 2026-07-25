from __future__ import annotations

import threading
from pathlib import Path

import pytest

from openai_tts_gui.errors import TTSCancelledError, TTSChunkError
from openai_tts_gui.tts import RunState
from openai_tts_gui.tts._publication import ChunkRequestMeta, ChunkTask
from openai_tts_gui.tts._scheduler import (
    RunCoordinator,
    ScheduledBatch,
    generate_parallel,
    generate_serial,
)


def test_parallel_scheduler_aborts_peer_work_after_an_internal_chunk_failure(
    tmp_path: Path,
) -> None:
    # Given: two simultaneous workers where the first domain failure must abort its peer.
    tasks = (
        ChunkTask(1, "failing", tmp_path / "first.wav"),
        ChunkTask(2, "blocked", tmp_path / "second.wav"),
    )
    abort_event = threading.Event()
    started = threading.Barrier(2)
    batch = ScheduledBatch(
        tasks,
        {},
        {1, 2},
        threading.Lock(),
        None,
        None,
        None,
        abort_event,
    )

    def run_chunk(*, task: ChunkTask) -> ChunkRequestMeta:
        started.wait(timeout=1.0)
        if task.index == 1:
            raise TTSChunkError("provider failed", chunk_index=1, file_path=str(task.filename))
        assert abort_event.wait(1.0)
        raise TTSCancelledError("peer aborted")

    # When: the first task fails after both workers have entered the scheduler.
    with pytest.raises(TTSChunkError, match="provider failed"):
        generate_parallel(batch, run_chunk, RunCoordinator(2), abort_event)

    # Then: the internal abort is published and no partial receipt survives for publication.
    assert abort_event.is_set()
    assert batch.metadata == {}


def test_serial_scheduler_rejects_cancelled_run_before_calling_runner(tmp_path: Path) -> None:
    state = RunState(1, None)
    state.request_cancel()
    batch = ScheduledBatch(
        (ChunkTask(1, "cancelled", tmp_path / "chunk.wav"),),
        {},
        {1},
        threading.Lock(),
        None,
        None,
        None,
        state.cancel_event,
        state=state,
    )

    def runner(*, task: ChunkTask) -> ChunkRequestMeta:
        raise AssertionError(f"cancelled scheduler invoked chunk {task.index}")

    with pytest.raises(TTSCancelledError):
        generate_serial(batch, runner)


def test_parallel_scheduler_records_callbacks_for_admitted_work(tmp_path: Path) -> None:
    tasks = (
        ChunkTask(1, "first", tmp_path / "first.wav"),
        ChunkTask(2, "second", tmp_path / "second.wav"),
    )
    progress: list[int] = []
    accepted: list[ChunkRequestMeta] = []
    between_chunks: list[str] = []
    state = RunState(2, None)
    batch = ScheduledBatch(
        tasks,
        {},
        {1, 2},
        threading.Lock(),
        progress.append,
        None,
        None,
        state.cancel_event,
        accepted.append,
        lambda: between_chunks.append("complete"),
        state,
    )

    def runner(*, task: ChunkTask) -> ChunkRequestMeta:
        return ChunkRequestMeta(task.index, f"request-{task.index}", None, str(task.filename), 1, 1)

    generate_parallel(batch, runner, RunCoordinator(2), None)

    assert set(batch.metadata) == {1, 2}
    assert {meta.chunk_index for meta in accepted} == {1, 2}
    assert progress == [47, 95]
    assert between_chunks == ["complete"]


def test_parallel_scheduler_cancels_queued_future_without_running_it(tmp_path: Path) -> None:
    tasks = (
        ChunkTask(1, "running", tmp_path / "first.wav"),
        ChunkTask(2, "queued", tmp_path / "second.wav"),
    )
    state = RunState(2, None)
    first_started = threading.Event()
    release_first = threading.Event()
    terminal = threading.Event()
    errors: list[TTSCancelledError] = []
    batch = ScheduledBatch(
        tasks,
        {},
        {1, 2},
        threading.Lock(),
        None,
        None,
        None,
        state.cancel_event,
        state=state,
    )

    def runner(*, task: ChunkTask) -> ChunkRequestMeta:
        if task.index == 2:
            raise AssertionError("queued task was executed after cancellation")
        first_started.set()
        assert release_first.wait(1.0)
        return ChunkRequestMeta(1, "request-1", None, str(task.filename), 1, 1)

    def generate() -> None:
        try:
            generate_parallel(batch, runner, RunCoordinator(1), None)
        except TTSCancelledError as error:
            errors.append(error)
        finally:
            terminal.set()

    worker = threading.Thread(target=generate)
    worker.start()
    assert first_started.wait(1.0)
    state.request_cancel()
    release_first.set()
    assert terminal.wait(1.0)
    worker.join(timeout=1.0)

    assert len(errors) == 1
    assert state._queued == {}
