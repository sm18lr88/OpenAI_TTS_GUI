from __future__ import annotations

import threading
from collections.abc import Callable

from ..errors import ContractError
from ._outcomes import CancellationStage, RunAccounting
from ._run_state_models import AttemptKey, ClosableResponse, FfmpegStopper, RunPhase
from ._run_state_resources import RunStateResources

__all__ = ["AttemptKey", "FfmpegStopper", "RunPhase", "RunState"]


class RunState(RunStateResources):
    """Track mutable resources and final accounting for one generation run."""

    def __init__(self, planned_chunks: int, cancel_event: threading.Event | None) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._planned_chunks = planned_chunks
        self._ingress_event = cancel_event
        self._cancel_event = threading.Event()
        self._attempted: set[int] = set()
        self._in_flight: set[int] = set()
        self._definitive: set[int] = set()
        self._uncertain: set[int] = set()
        self._attempt_count = 0
        self._completed: dict[int, str | None] = {}
        self._request_ids: list[str] = []
        self._phase = RunPhase.RUNNING
        self._cancellation_stage = CancellationStage.NONE
        self._admissions_open = True
        self._frozen = False
        self._queued: dict[int, Callable[[], bool] | None] = {}
        self._admitted: set[int] = set()
        self._awaiting: set[AttemptKey] = set()
        self._responses: dict[AttemptKey, ClosableResponse] = {}
        self._validated_results: set[AttemptKey] = set()
        self._retry_waits: set[AttemptKey] = set()
        self._ffmpeg: FfmpegStopper | None = None
        self._publication_active = False
        self._between_chunks = False
        self._warnings: list[str] = []

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    @property
    def phase(self) -> RunPhase:
        with self._lock:
            return self._phase

    @property
    def cleanup_warnings(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._warnings)

    def bind_plan(self, planned_chunks: int) -> None:
        with self._lock:
            if self._planned_chunks != 0 or self._frozen:
                raise ContractError("Run plan is already bound.")
            self._planned_chunks = planned_chunks

    def sync_ingress_cancel(self) -> bool:
        if self._ingress_event is not None and self._ingress_event.is_set():
            self.request_cancel()
        return self._cancel_event.is_set()

    def cancellation_requested(self) -> bool:
        return self.sync_ingress_cancel()

    def reserve(self, index: int) -> bool:
        with self._lock:
            if not self._admissions_open:
                return False
            self._queued[index] = None
            self._condition.notify_all()
            return True

    def attach(self, index: int, cancel: Callable[[], bool]) -> bool:
        with self._lock:
            if index not in self._queued:
                raise ContractError("Queued cancellation requires a reserved task.")
            self._queued[index] = cancel
            self._condition.notify_all()
            return self._admissions_open

    def admit(self, index: int) -> bool:
        with self._lock:
            self._queued.pop(index, None)
            if not self._admissions_open:
                self._condition.notify_all()
                return False
            self._admitted.add(index)
            self._condition.notify_all()
            return True

    def leave_admission(self, index: int) -> None:
        with self._lock:
            self._admitted.discard(index)
            self._condition.notify_all()

    def discard_queued(self, index: int) -> None:
        with self._lock:
            self._queued.pop(index, None)
            self._condition.notify_all()

    def begin_attempt(self, key: AttemptKey) -> bool:
        with self._lock:
            if not self._admissions_open:
                return False
            self._attempted.add(key.chunk_index)
            self._in_flight.add(key.chunk_index)
            self._attempt_count += 1
            self._awaiting.add(key)
            self._condition.notify_all()
            return True

    def register_response(self, key: AttemptKey, response: ClosableResponse) -> bool:
        with self._lock:
            if key not in self._awaiting:
                raise ContractError("A response requires a registered awaiting attempt.")
            self._awaiting.remove(key)
            self._responses[key] = response
            self._condition.notify_all()
            return self._admissions_open

    def validate_result(self, key: AttemptKey) -> None:
        with self._lock:
            self._awaiting.discard(key)
            self._responses.pop(key, None)
            self._validated_results.add(key)
            self._condition.notify_all()

    def accept_validated_result(self, key: AttemptKey, request_id: str | None) -> None:
        with self._lock:
            if key not in self._validated_results:
                raise ContractError("An accepted result requires validated provider ownership.")
            self._validated_results.remove(key)
            self._in_flight.discard(key.chunk_index)
            self._record_completed_locked(key.chunk_index, request_id)
            self._condition.notify_all()

    def complete_attempt(self, key: AttemptKey) -> None:
        with self._lock:
            self._awaiting.discard(key)
            self._responses.pop(key, None)
            self._validated_results.discard(key)
            self._in_flight.discard(key.chunk_index)
            self._condition.notify_all()

    def transition_attempt_to_retry_wait(self, key: AttemptKey) -> None:
        with self._lock:
            self._awaiting.discard(key)
            self._responses.pop(key, None)
            self._validated_results.discard(key)
            self._in_flight.discard(key.chunk_index)
            self._definitive.add(key.chunk_index)
            self._uncertain.discard(key.chunk_index)
            self._retry_waits.add(key)
            self._condition.notify_all()

    def finish_retry_wait(self, key: AttemptKey) -> None:
        with self._lock:
            self._retry_waits.discard(key)
            self._condition.notify_all()

    def mark_definitive(self, index: int) -> None:
        with self._lock:
            self._definitive.add(index)
            self._uncertain.discard(index)

    def mark_uncertain(self, index: int) -> None:
        with self._lock:
            self._definitive.discard(index)
            self._uncertain.add(index)

    def record_request_id(self, request_id: str | None) -> None:
        if request_id is not None and request_id.strip():
            with self._lock:
                if request_id.strip() not in self._request_ids:
                    self._request_ids.append(request_id.strip())

    def reconcile_completed_attempt(self, index: int, attempts: int) -> None:
        with self._lock:
            if index not in self._attempted:
                self._attempted.add(index)
                self._attempt_count += attempts

    def _record_completed_locked(self, index: int, request_id: str | None) -> None:
        if index not in self._attempted:
            raise ContractError("A completed chunk requires a recorded started attempt.")
        self._completed[index] = request_id
        self._definitive.discard(index)
        self._uncertain.discard(index)
        self._between_chunks = True
        if request_id is not None and request_id.strip() and request_id not in self._request_ids:
            self._request_ids.append(request_id)

    def join(self) -> None:
        with self._lock:
            self._admissions_open = False
            if not self._publication_active:
                self._phase = RunPhase.JOINING
            while (
                self._queued
                or self._admitted
                or self._awaiting
                or self._responses
                or self._validated_results
                or self._retry_waits
                or self._ffmpeg
                or self._publication_active
            ):
                self._condition.wait()

    def freeze(self) -> RunAccounting:
        with self._lock:
            if self._publication_active:
                raise ContractError("Final accounting requires publication to finish.")
        self.join()
        with self._lock:
            if self._frozen:
                raise ContractError("Final accounting is already frozen.")
            if self._in_flight:
                raise ContractError("Final accounting requires no in-flight chunks.")
            self._frozen = True
            self._phase = RunPhase.TERMINAL
            return RunAccounting(
                self._planned_chunks,
                self._planned_chunks,
                self._attempt_count,
                len(self._completed),
                tuple(self._request_ids),
                tuple(sorted(self._uncertain - set(self._completed))),
                self._cancellation_stage,
                tuple(sorted(self._completed)),
            )
