from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import MAX_RETRIES
from ..errors import TTSCancelledError
from ._run_state import AttemptKey

if TYPE_CHECKING:
    from ._retry import RetryContext

MAX_ATTEMPTS_PER_CHUNK = MAX_RETRIES
MAX_429_RETRIES_PER_CHUNK = MAX_ATTEMPTS_PER_CHUNK - 1


def mark_definitive(context: RetryContext, key: AttemptKey) -> None:
    if context.run_state is not None:
        context.run_state.complete_attempt(key)
        context.run_state.mark_definitive(key.chunk_index)
    else:
        context.on_attempt_finished(key.chunk_index)
        context.on_attempt_definitive(key.chunk_index)


def mark_uncertain(context: RetryContext, key: AttemptKey) -> None:
    if context.run_state is not None:
        context.run_state.complete_attempt(key)
        context.run_state.mark_uncertain(key.chunk_index)
    else:
        context.on_attempt_finished(key.chunk_index)
        context.on_attempt_uncertain(key.chunk_index)


def raise_if_cancelled_after_truth(context: RetryContext) -> None:
    if context.run_state is not None and context.run_state.cancellation_requested():
        raise TTSCancelledError("TTS generation cancelled.")


def report_parallelism(context: RetryContext) -> None:
    if context.coordinator is not None and context.on_parallelism is not None:
        active_workers, worker_cap = context.coordinator.snapshot()
        context.on_parallelism(active_workers, worker_cap)
