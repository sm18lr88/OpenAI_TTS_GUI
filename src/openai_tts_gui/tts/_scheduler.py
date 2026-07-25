from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from ..errors import TTSCancelledError, TTSChunkError, TTSError
from ._publication import ChunkRequestMeta, ChunkTask
from ._run_state import RunState


class RunCoordinator:
    def __init__(self, initial_cap: int) -> None:
        self._condition = threading.Condition()
        self.active_permits = 0
        self.current_cap = max(1, initial_cap)
        self.next_allowed_at = 0.0

    def acquire(self, cancel_event: CancelEvent) -> None:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise TTSCancelledError("TTS generation cancelled.")
            with self._condition:
                cooldown_wait = max(0.0, self.next_allowed_at - time.monotonic())
                if self.active_permits < self.current_cap and cooldown_wait <= 0:
                    self.active_permits += 1
                    return
                wait_time = cooldown_wait if cooldown_wait > 0 else 0.01
            if cancel_event is None:
                time.sleep(wait_time)
            elif cancel_event.wait(wait_time):
                raise TTSCancelledError("TTS generation cancelled.")

    def release(self) -> None:
        with self._condition:
            if self.active_permits > 0:
                self.active_permits -= 1
            self._condition.notify_all()

    def apply_retry_wait(self, wait_time: float, *, reduce_cap: bool) -> None:
        with self._condition:
            self.next_allowed_at = max(self.next_allowed_at, time.monotonic() + max(0.0, wait_time))
            if reduce_cap:
                self.current_cap = max(1, self.current_cap - 1)
            self._condition.notify_all()

    def snapshot(self) -> tuple[int, int]:
        with self._condition:
            return self.active_permits, self.current_cap


class CombinedCancelEvent:
    def __init__(self, *events: threading.Event | None) -> None:
        self._events = [event for event in events if event is not None]

    def is_set(self) -> bool:
        return any(event.is_set() for event in self._events)

    def wait(self, timeout: float) -> bool:
        if self.is_set():
            return True
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self.is_set():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self.is_set()
            time.sleep(min(0.01, remaining))


CancelEvent = threading.Event | CombinedCancelEvent | None
ChunkRunner = Callable[..., ChunkRequestMeta]


@dataclass(frozen=True, slots=True)
class ScheduledBatch:
    tasks: tuple[ChunkTask, ...]
    metadata: dict[int, ChunkRequestMeta]
    expected_indexes: set[int]
    metadata_lock: threading.Lock
    on_progress: Callable[[int], None] | None
    on_status: Callable[[str], None] | None
    on_parallelism: Callable[[int, int], None] | None
    cancel_event: CancelEvent
    on_accepted: Callable[[ChunkRequestMeta], None] | None = None
    on_between_chunks: Callable[[], None] | None = None
    state: RunState | None = None


def generate_serial(batch: ScheduledBatch, runner: ChunkRunner) -> None:
    total_chunks = len(batch.tasks)
    for task in batch.tasks:
        if batch.state is not None and not batch.state.admit(task.index):
            raise TTSCancelledError("TTS generation cancelled.")
        ensure_not_cancelled(batch.cancel_event)
        try:
            if batch.on_status:
                batch.on_status(f"Generating chunk {task.index}/{total_chunks}")
            if batch.on_parallelism:
                batch.on_parallelism(1, 1)
            metadata = runner(task=task)
            record_metadata(
                meta=metadata,
                chunk_meta=batch.metadata,
                expected_indexes=batch.expected_indexes,
                meta_lock=batch.metadata_lock,
            )
            if batch.on_accepted is not None:
                batch.on_accepted(metadata)
            if batch.on_between_chunks is not None:
                batch.on_between_chunks()
            if batch.on_progress:
                batch.on_progress(int((task.index / total_chunks) * 95))
        finally:
            if batch.state is not None:
                batch.state.leave_admission(task.index)
    if batch.on_parallelism:
        batch.on_parallelism(0, 1)


def generate_parallel(
    batch: ScheduledBatch,
    runner: ChunkRunner,
    coordinator: RunCoordinator,
    abort_event: threading.Event | None,
) -> None:
    completed = 0
    futures: dict[Future[ChunkRequestMeta], ChunkTask] = {}
    with ThreadPoolExecutor(max_workers=min(coordinator.current_cap, len(batch.tasks))) as executor:
        for task in batch.tasks:
            if batch.state is not None and not batch.state.reserve(task.index):
                break
            start = threading.Event()

            def admitted_runner(
                *, item: ChunkTask = task, start_event: threading.Event = start
            ) -> ChunkRequestMeta:
                start_event.wait()
                if batch.state is not None and not batch.state.admit(item.index):
                    raise TTSCancelledError("TTS generation cancelled.")
                try:
                    return runner(task=item)
                finally:
                    if batch.state is not None:
                        batch.state.leave_admission(item.index)

            future = executor.submit(admitted_runner)
            state = batch.state
            if state is not None:

                def cancel_work(
                    item: ChunkTask = task,
                    work: Future[ChunkRequestMeta] = future,
                    owner: RunState = state,
                ) -> bool:
                    cancelled = work.cancel()
                    if cancelled:
                        owner.discard_queued(item.index)
                    return cancelled

                if not state.attach(task.index, cancel_work):
                    cancel_work()
            start.set()
            futures[future] = task
        try:
            for future in as_completed(futures):
                ensure_not_cancelled(batch.cancel_event)
                result = future.result()
                record_metadata(
                    meta=result,
                    chunk_meta=batch.metadata,
                    expected_indexes=batch.expected_indexes,
                    meta_lock=batch.metadata_lock,
                )
                if batch.on_accepted is not None:
                    batch.on_accepted(result)
                completed += 1
                if batch.on_progress:
                    batch.on_progress(int((completed / len(batch.tasks)) * 95))
            if batch.on_between_chunks is not None:
                batch.on_between_chunks()
        except TTSError as error:
            if abort_event is not None:
                abort_event.set()
            for future in futures:
                future.cancel()
            executor.shutdown(wait=True, cancel_futures=True)
            if batch.state is not None:
                for task in futures.values():
                    batch.state.discard_queued(task.index)
            if not isinstance(error, TTSCancelledError) and (
                batch.state is None or not batch.state.cancellation_requested()
            ):
                for future in futures:
                    if future.cancelled():
                        continue
                    try:
                        result = future.result()
                    except TTSError:
                        continue
                    if result.chunk_index in batch.metadata:
                        continue
                    record_metadata(
                        meta=result,
                        chunk_meta=batch.metadata,
                        expected_indexes=batch.expected_indexes,
                        meta_lock=batch.metadata_lock,
                    )
                    if batch.on_accepted is not None:
                        batch.on_accepted(result)
            raise


def ensure_not_cancelled(cancel_event: CancelEvent) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TTSCancelledError("TTS generation cancelled.")


def record_metadata(
    *,
    meta: ChunkRequestMeta,
    chunk_meta: dict[int, ChunkRequestMeta],
    expected_indexes: set[int],
    meta_lock: threading.Lock,
) -> None:
    with meta_lock:
        if meta.chunk_index not in expected_indexes:
            raise TTSChunkError(
                f"Unexpected chunk result index {meta.chunk_index} during finalization.",
                chunk_index=meta.chunk_index,
                file_path=meta.file,
            )
        if meta.chunk_index in chunk_meta:
            raise TTSChunkError(
                f"Duplicate chunk result for chunk {meta.chunk_index} detected before concat.",
                chunk_index=meta.chunk_index,
                file_path=meta.file,
            )
        chunk_meta[meta.chunk_index] = meta


def ordered_metadata(
    tasks: list[ChunkTask] | tuple[ChunkTask, ...], chunk_meta: dict[int, ChunkRequestMeta]
) -> list[ChunkRequestMeta]:
    ordered: list[ChunkRequestMeta] = []
    missing: list[int] = []
    for task in tasks:
        item = chunk_meta.get(task.index)
        if item is None:
            missing.append(task.index)
            continue
        ordered.append(item)
    if missing:
        raise TTSChunkError(
            "Missing successful chunk result(s) before concat: "
            + ", ".join(str(index) for index in missing)
        )
    return ordered
