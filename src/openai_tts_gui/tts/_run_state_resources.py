from __future__ import annotations

from typing import TYPE_CHECKING

from ..errors import ContractError
from ._outcomes import CancellationStage, PublicationInProgress
from ._run_state_models import CancelActions, FfmpegStopper, RunPhase

if TYPE_CHECKING:
    from ._run_state import RunState


class RunStateResources:
    def begin_ffmpeg(self: RunState, stopper: FfmpegStopper) -> bool:
        with self._lock:
            self._ffmpeg = stopper
            self._condition.notify_all()
            return self._admissions_open

    def finish_ffmpeg(self: RunState) -> None:
        with self._lock:
            self._ffmpeg = None
            self._condition.notify_all()

    def begin_publication(self: RunState) -> CancellationStage | PublicationInProgress:
        with self._lock:
            if self._frozen:
                raise ContractError("Frozen runs cannot begin publication.")
            ingress_cancelled = self._ingress_event is not None and self._ingress_event.is_set()
            if ingress_cancelled or self._cancel_event.is_set():
                actions = self._request_cancel_locked()
                decision: CancellationStage | PublicationInProgress = self._cancellation_stage
            elif self._cancellation_stage is not CancellationStage.NONE:
                actions = CancelActions((), (), None)
                decision = self._cancellation_stage
            else:
                actions = CancelActions((), (), None)
                self._publication_active = True
                self._phase = RunPhase.PUBLISHING
                self._condition.notify_all()
                decision = PublicationInProgress()
        self._apply_cancel_actions(actions)
        return decision

    def finish_publication(self: RunState) -> None:
        with self._lock:
            self._publication_active = False
            if self._phase is RunPhase.PUBLISHING:
                self._phase = RunPhase.RUNNING
            self._condition.notify_all()

    def request_cancel(self: RunState) -> CancellationStage | PublicationInProgress:
        with self._lock:
            if self._frozen:
                return self._cancellation_stage
            if self._publication_active:
                return PublicationInProgress()
            actions = self._request_cancel_locked()
        self._apply_cancel_actions(actions)
        return self._cancellation_stage

    def _request_cancel_locked(self: RunState) -> CancelActions:
        if self._cancellation_stage is not CancellationStage.NONE:
            return CancelActions((), (), None)
        self._cancellation_stage = self._stage_locked()
        self._phase = RunPhase.CANCELLING
        self._admissions_open = False
        self._cancel_event.set()
        for key in self._validated_results:
            self._in_flight.discard(key.chunk_index)
        self._validated_results.clear()
        actions = CancelActions(
            tuple(item for item in self._queued.values() if item),
            tuple(self._responses.values()),
            self._ffmpeg,
        )
        self._condition.notify_all()
        return actions

    def _stage_locked(self: RunState) -> CancellationStage:
        if self._awaiting:
            return CancellationStage.AWAITING_PROVIDER_RESPONSE
        if self._responses or self._validated_results:
            return CancellationStage.DURING_PROVIDER_STREAM
        if self._retry_waits:
            return CancellationStage.DURING_RETRY_WAIT
        if self._ffmpeg is not None:
            return CancellationStage.DURING_FFMPEG
        if self._planned_chunks and len(self._completed) == self._planned_chunks:
            return CancellationStage.BEFORE_PUBLICATION
        if self._between_chunks:
            return CancellationStage.BETWEEN_CHUNKS
        return CancellationStage.BEFORE_REQUEST

    def _apply_cancel_actions(self: RunState, actions: CancelActions) -> None:
        for action in actions.futures:
            try:
                action()
            except RuntimeError as exc:
                self._record_warning(f"queued cancellation failed: {exc}")
        for response in actions.responses:
            try:
                response.close()
            except (OSError, RuntimeError) as exc:
                self._record_warning(f"response close failed: {exc}")
        if actions.ffmpeg is not None:
            try:
                actions.ffmpeg.request_stop()
            except (OSError, RuntimeError) as exc:
                self._record_warning(f"ffmpeg stop failed: {exc}")

    def _record_warning(self: RunState, warning: str) -> None:
        with self._lock:
            self._warnings.append(warning)
