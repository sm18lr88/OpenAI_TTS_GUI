from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from .. import config
from ..core import (
    cleanup_files,
    concatenate_audio_files,
    preflight_check,
    sha256_text,
    split_text,
    write_sidecar_metadata,
)
from ..errors import (
    ConcurrentRunError,
    ContractError,
    FFmpegError,
    FFmpegNotFoundError,
    TTSCancelledError,
)
from . import _execution, _publication, _retry, _scheduler
from ._contracts import (
    CancellationStage,
    GenerationConfig,
    GenerationHooks,
    GenerationOutcome,
    GenerationProgress,
    GenerationRequest,
)
from ._legacy import ProgressCallback, progress_callback, project_contract_error, project_outcome
from ._outcomes import PublicationInProgress
from ._provider import (
    OpenAIProviderAdapter,
    ProviderStreamError,
    ThreadLocalClient,
    extract_response_metadata,
    load_openai_symbols,
)
from ._retry import (
    MAX_ATTEMPTS_PER_CHUNK,
    BackoffPolicy,
    ProviderErrorTypes,
    RetryContext,
    generate_with_retries,
)
from ._retry_state import MAX_429_RETRIES_PER_CHUNK
from ._run_state import RunState

StatusCallback = Callable[[str], None]
ParallelismCallback = Callable[[int, int], None]
NO_CANCELLATION = CancellationStage.NONE
_ChunkRequestMeta, _ChunkTask = _publication.ChunkRequestMeta, _publication.ChunkTask
_RunCoordinator, _CombinedCancelEvent = _scheduler.RunCoordinator, _scheduler.CombinedCancelEvent
(
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
) = load_openai_symbols()


def require_preflight() -> str:
    ok, detail = preflight_check()
    if ok:
        return detail
    if "not found" in detail.lower():
        raise FFmpegNotFoundError(detail)
    raise FFmpegError(detail)


def compute_backoff(error: Exception, attempt: int) -> float:
    return _retry.compute_backoff(
        error,
        attempt,
        BackoffPolicy(float(config.settings.RETRY_DELAY), random.uniform),
    )


class TTSService:
    def __init__(self, api_key: str, base_url: str | None = None, timeout: float = 60.0) -> None:
        self._api_key = api_key or None
        self._base_url = base_url
        self._timeout = timeout
        self._provider = ThreadLocalClient(threading.local(), self._build_client)
        self._speech_provider = OpenAIProviderAdapter(lambda: self._get_client())
        self._last_run_coordinator: _RunCoordinator | None = None
        self._run_lock = threading.Lock()
        self._active_run_state: RunState | None = None

    def _build_client(self):
        return OpenAI(
            api_key=self._api_key,
            timeout=self._timeout,
            base_url=self._base_url,
            max_retries=0,
        )

    def _get_client(self):
        return self._provider.get_client()

    @property
    def max_attempts_per_chunk(self) -> int:
        return MAX_ATTEMPTS_PER_CHUNK

    @property
    def max_429_retries_per_chunk(self) -> int:
        return MAX_429_RETRIES_PER_CHUNK

    def request_cancel(self) -> CancellationStage | PublicationInProgress:
        with self._run_lock:
            state = self._active_run_state
        return state.request_cancel() if state is not None else NO_CANCELLATION

    def execute(
        self, request: GenerationRequest, hooks: GenerationHooks | None = None
    ) -> GenerationOutcome:
        return _execution.run(
            self,
            request,
            hooks or GenerationHooks(),
            _execution.ExecutionDependencies(
                require_preflight,
                split_text,
                concatenate_audio_files,
                cleanup_files,
                write_sidecar_metadata,
                sha256_text,
            ),
        )

    def generate(
        self,
        *,
        text: str,
        output_path: str,
        model: str = "tts-1",
        voice: str = "alloy",
        response_format: str = "mp3",
        speed: float = 1.0,
        instructions: str = "",
        parallelism: int | None = None,
        retain_files: bool = False,
        on_progress: ProgressCallback | None = None,
        on_status: StatusCallback | None = None,
        on_parallelism: ParallelismCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event is not None and cancel_event.is_set():
            raise TTSCancelledError("TTS generation cancelled.")
        try:
            request = GenerationRequest(
                text,
                output_path,
                GenerationConfig(
                    model,
                    voice,
                    response_format,
                    speed,
                    instructions,
                    parallelism,
                    retain_files,
                ),
            )
        except ContractError as exc:
            raise project_contract_error(exc) from exc
        progress_total = [1]
        outcome = self.execute(
            request,
            GenerationHooks(
                progress_callback(on_progress, progress_total),
                on_status,
                on_parallelism,
                cancel_event,
            ),
        )
        return project_outcome(outcome)

    def _generate_chunk_with_retries(
        self,
        *,
        task: _ChunkTask,
        config: GenerationConfig | None = None,
        model: str | None = None,
        voice: str | None = None,
        response_format: str | None = None,
        speed: float | None = None,
        instructions: str | None = None,
        on_status: StatusCallback | None = None,
        on_parallelism: ParallelismCallback | None = None,
        on_progress: Callable[[GenerationProgress], None] | None = None,
        cancel_event: _scheduler.CancelEvent = None,
        coordinator: _RunCoordinator | None = None,
        state: RunState | None = None,
    ) -> _ChunkRequestMeta:
        run_config = config or GenerationConfig(
            model or "tts-1",
            voice or "alloy",
            response_format or "mp3",
            speed if speed is not None else 1.0,
            instructions or "",
        )
        return generate_with_retries(
            RetryContext(
                task=task,
                config=run_config,
                provider=self._speech_provider,
                cancel_event=cancel_event,
                coordinator=coordinator,
                on_status=on_status,
                on_parallelism=on_parallelism,
                on_progress=on_progress,
                errors=ProviderErrorTypes(
                    RateLimitError,
                    APITimeoutError,
                    APIConnectionError,
                    APIStatusError,
                    APIError,
                    OpenAIError,
                    ProviderStreamError,
                ),
                sleep_with_cancel=self._sleep_with_cancel,
                compute_backoff=compute_backoff,
                on_attempt_started=lambda _index: None,
                on_attempt_finished=lambda _index: None,
                on_attempt_definitive=lambda _index: None,
                on_attempt_uncertain=lambda _index: None,
                on_request_id=(
                    state.record_request_id if state is not None else self._record_request_id
                ),
                on_stage=lambda _stage: None,
                run_state=state,
            )
        )

    def _activate_run(self, state: RunState) -> None:
        with self._run_lock:
            if self._active_run_state is not None:
                raise ConcurrentRunError("This TTS service already has an active run.")
            self._active_run_state = state

    def _deactivate_run(self, state: RunState) -> None:
        with self._run_lock:
            if self._active_run_state is state:
                self._active_run_state = None

    @staticmethod
    def _record_request_id(_request_id: str | None) -> None:
        return None

    @staticmethod
    def _attempt_started(_index: int) -> None:
        return None

    @staticmethod
    def _attempt_finished(_index: int) -> None:
        return None

    def _sleep_with_cancel(self, wait_time: float, cancel_event: _scheduler.CancelEvent) -> None:
        if cancel_event is None:
            time.sleep(wait_time)
        elif cancel_event.wait(wait_time):
            raise TTSCancelledError("TTS generation cancelled.")

    _extract_response_metadata = staticmethod(extract_response_metadata)

    _record_chunk_meta = staticmethod(_scheduler.record_metadata)
    _ordered_chunk_meta = staticmethod(_scheduler.ordered_metadata)
    _with_retained_dir = staticmethod(_publication.with_retained_dir)
