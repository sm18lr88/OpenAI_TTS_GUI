from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from ..errors import TTSAPIError, TTSCancelledError, TTSChunkError
from ._contracts import (
    CancellationStage,
    ChunkStarted,
    GenerationConfig,
    GenerationProgress,
    ProviderRequest,
    RetryWaiting,
)
from ._provider import ProviderStreamError, SpeechProvider
from ._publication import ChunkRequestMeta, ChunkTask
from ._retry_state import MAX_ATTEMPTS_PER_CHUNK
from ._retry_state import mark_definitive as _mark_definitive
from ._retry_state import mark_uncertain as _mark_uncertain
from ._retry_state import raise_if_cancelled_after_truth as _raise_if_cancelled_after_truth
from ._retry_state import report_parallelism as _report_parallelism
from ._run_state import AttemptKey, RunState
from ._scheduler import CancelEvent, RunCoordinator


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    retry_delay: float
    jitter: Callable[[float, float], float]


@dataclass(frozen=True, slots=True)
class ProviderErrorTypes:
    rate_limit: type[Exception]
    timeout: type[Exception]
    connection: type[Exception]
    status: type[Exception]
    api: type[Exception]
    openai: type[Exception]
    stream: type[ProviderStreamError]


@dataclass(frozen=True, slots=True)
class RetryContext:
    task: ChunkTask
    config: GenerationConfig
    provider: SpeechProvider
    cancel_event: CancelEvent
    coordinator: RunCoordinator | None
    on_status: Callable[[str], None] | None
    on_parallelism: Callable[[int, int], None] | None
    on_progress: Callable[[GenerationProgress], None] | None
    errors: ProviderErrorTypes
    sleep_with_cancel: Callable[[float, CancelEvent], None]
    compute_backoff: Callable[[Exception, int], float]
    on_attempt_started: Callable[[int], None]
    on_attempt_finished: Callable[[int], None]
    on_attempt_definitive: Callable[[int], None]
    on_attempt_uncertain: Callable[[int], None]
    on_request_id: Callable[[str | None], None]
    on_stage: Callable[[CancellationStage], None]
    run_state: RunState | None = None


def compute_backoff(error: Exception, attempt: int, policy: BackoffPolicy) -> float:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            retry_after_ms = _valid_delay(headers.get("retry-after-ms"), 1000.0)
            if retry_after_ms is not None:
                return retry_after_ms
            retry_after = _valid_delay(headers.get("retry-after"), 1.0)
            if retry_after is not None:
                return retry_after
        except (OSError, TypeError, ValueError):
            pass
    delay = max(1.0, policy.retry_delay) * (2**attempt)
    return delay + policy.jitter(0, 0.2 * delay)


def _valid_delay(raw: str | None, divisor: float) -> float | None:
    if not isinstance(raw, str):
        return None
    try:
        value = float(raw) / divisor
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def generate_with_retries(context: RetryContext) -> ChunkRequestMeta:
    request = ProviderRequest(
        context.task.index,
        context.task.text,
        str(context.task.filename),
        context.config,
    )
    for attempt in range(1, MAX_ATTEMPTS_PER_CHUNK + 1):
        _ensure_not_cancelled(context.cancel_event)
        permit_acquired = _acquire(context)
        try:
            _emit_progress(context, ChunkStarted(context.task.index, attempt))
            key = AttemptKey(context.task.index, attempt)
            if context.run_state is None:
                context.on_attempt_started(context.task.index)
            try:
                receipt = context.provider.stream(request, context.on_stage, context.run_state, key)
            except context.errors.rate_limit as exc:
                _handle_rate_limit(context, attempt, exc, key)
                continue
            except context.errors.timeout as exc:
                _raise_uncertain_provider_error(context, exc, key=key)
            except context.errors.connection as exc:
                _raise_uncertain_provider_error(context, exc, key=key)
            except context.errors.status as exc:
                _handle_status_error(context, attempt, exc, key)
            except context.errors.api as exc:
                _raise_uncertain_provider_error(context, exc, key=key)
            except context.errors.openai as exc:
                _raise_uncertain_provider_error(context, exc, key=key)
            except context.errors.stream as exc:
                _mark_uncertain(context, key)
                context.on_request_id(exc.request_id)
                _raise_if_cancelled_after_truth(context)
                raise TTSChunkError(
                    f"Provider stream failed for chunk {context.task.index}: {exc}",
                    chunk_index=context.task.index,
                    file_path=str(context.task.filename),
                ) from exc
            except OSError as exc:
                _mark_uncertain(context, key)
                _raise_if_cancelled_after_truth(context)
                raise TTSChunkError(
                    f"File saving error for chunk {context.task.index}: {exc}",
                    chunk_index=context.task.index,
                    file_path=str(context.task.filename),
                ) from exc
            context.on_request_id(receipt.request_id)
            return ChunkRequestMeta(
                context.task.index,
                receipt.request_id,
                receipt.model_header,
                str(context.task.filename),
                attempt,
                len(context.task.text),
                dict(receipt.retry_headers) or None,
            )
        finally:
            if permit_acquired:
                _release(context)
    raise TTSChunkError(
        f"Failed to save chunk {context.task.index} after {MAX_ATTEMPTS_PER_CHUNK} attempts.",
        chunk_index=context.task.index,
        file_path=str(context.task.filename),
    )


def _acquire(context: RetryContext) -> bool:
    if context.coordinator is None:
        return False
    context.coordinator.acquire(context.cancel_event)
    _report_parallelism(context)
    return True


def _release(context: RetryContext) -> None:
    if context.coordinator is not None:
        context.coordinator.release()
        _report_parallelism(context)


def _handle_rate_limit(
    context: RetryContext, attempt: int, error: Exception, key: AttemptKey
) -> None:
    status_code = _status_code(error)
    request_id = _capture_request_id(context, error)
    if status_code != 429:
        _raise_uncertain_provider_error(context, error, request_id=request_id, key=key)
    if attempt >= MAX_ATTEMPTS_PER_CHUNK:
        _mark_definitive(context, key)
        _raise_if_cancelled_after_truth(context)
        raise TTSAPIError(
            f"Rate limit persisted after {attempt} attempts while generating chunk "
            f"{context.task.index}.",
            status_code=429,
            request_id=request_id,
        ) from error
    _wait_for_retry(context, attempt, error, True, "rate limited", key)


def _handle_status_error(
    context: RetryContext, attempt: int, error: Exception, key: AttemptKey
) -> None:
    status = _status_code(error)
    request_id = _capture_request_id(context, error)
    if status == 429:
        if attempt < MAX_ATTEMPTS_PER_CHUNK:
            _wait_for_retry(context, attempt, error, True, "rate limited", key)
            return
        _mark_definitive(context, key)
    elif status is not None and 400 <= status < 500:
        _mark_definitive(context, key)
    else:
        _mark_uncertain(context, key)
    _raise_provider_error(context, error, status, request_id)


def _raise_uncertain_provider_error(
    context: RetryContext, error: Exception, *, request_id: str | None = None, key: AttemptKey
) -> None:
    _mark_uncertain(context, key)
    _raise_if_cancelled_after_truth(context)
    _raise_provider_error(
        context,
        error,
        _status_code(error),
        request_id if request_id is not None else _capture_request_id(context, error),
    )


def _raise_provider_error(
    context: RetryContext, error: Exception, status: int | None, request_id: str | None
) -> None:
    detail = f"API Error while generating chunk {context.task.index}: {error}"
    if status is not None:
        detail += f" (Status code: {status})"
    if request_id is not None:
        detail += f" [request id: {request_id}]"
    raise TTSAPIError(detail, status_code=status, request_id=request_id) from error


def _status_code(error: Exception) -> int | None:
    status = getattr(error, "status_code", None)
    return status if type(status) is int else None


def _capture_request_id(context: RetryContext, error: Exception) -> str | None:
    request_id = getattr(error, "request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        normalized = request_id.strip()
        context.on_request_id(normalized)
        return normalized
    return None


def _wait_for_retry(
    context: RetryContext,
    attempt: int,
    error: Exception,
    reduce_cap: bool,
    label: str,
    key: AttemptKey,
) -> None:
    wait_time = context.compute_backoff(error, attempt - 1)
    if context.run_state is not None:
        context.run_state.transition_attempt_to_retry_wait(key)
    else:
        context.on_stage(CancellationStage.DURING_RETRY_WAIT)
    if context.coordinator is not None:
        context.coordinator.apply_retry_wait(wait_time, reduce_cap=reduce_cap)
        _report_parallelism(context)
    if context.on_status is not None:
        context.on_status(f"Chunk {context.task.index}: {label}; retrying in {wait_time:.1f}s")
    _emit_progress(context, RetryWaiting(context.task.index, attempt, wait_time))
    try:
        context.sleep_with_cancel(wait_time, context.cancel_event)
    finally:
        if context.run_state is not None:
            context.run_state.finish_retry_wait(key)


def _ensure_not_cancelled(cancel_event: CancelEvent) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TTSCancelledError("TTS generation cancelled.")


def _emit_progress(context: RetryContext, progress: GenerationProgress) -> None:
    if context.on_progress is not None:
        context.on_progress(progress)
