from __future__ import annotations

from ..errors import TTSCancelledError
from ._contracts import ChunkCompleted, GenerationHooks, GenerationProgress
from ._publication import ChunkRequestMeta
from ._run_state import AttemptKey, RunState


def raise_if_cancelled(state: RunState) -> None:
    if state.cancellation_requested():
        raise TTSCancelledError("TTS generation cancelled.")


def emit(hooks: GenerationHooks, progress: GenerationProgress) -> None:
    if hooks.on_progress is not None:
        hooks.on_progress(progress)


def accept(state: RunState, hooks: GenerationHooks, item: ChunkRequestMeta) -> None:
    state.reconcile_completed_attempt(item.chunk_index, item.attempts)
    state.accept_validated_result(AttemptKey(item.chunk_index, item.attempts), item.request_id)
    emit(hooks, ChunkCompleted(item.chunk_index, item.request_id))
