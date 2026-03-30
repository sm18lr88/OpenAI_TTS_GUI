from __future__ import annotations

import logging
import math
import random
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

try:
    from openai import (
        APIConnectionError,
        APIError,
        APIStatusError,
        APITimeoutError,
        OpenAI,
        OpenAIError,
        RateLimitError,
    )
except Exception as _openai_import_error:
    _OPENAI_IMPORT_ERROR = _openai_import_error

    class OpenAIError(Exception):
        pass

    class APIError(OpenAIError):
        pass

    class APIConnectionError(APIError):
        pass

    class APITimeoutError(APIError):
        pass

    class RateLimitError(APIError):
        pass

    class APIStatusError(APIError):
        def __init__(
            self,
            message: str = "",
            *,
            status_code: int | None = None,
            request_id: str | None = None,
        ) -> None:
            self.message = message
            self.status_code = status_code
            self.request_id = request_id
            super().__init__(message)

    class OpenAI:  # pragma: no cover - exercised only when dependency is missing
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError(
                "The 'openai' package is required to use TTSService."
            ) from _OPENAI_IMPORT_ERROR


from ..config import settings
from ..core.audio import cleanup_files, concatenate_audio_files
from ..core.ffmpeg import require_preflight
from ..core.metadata import sha256_text, write_sidecar_metadata
from ..core.text import split_text
from ..errors import ConfigError, TTSAPIError, TTSCancelledError, TTSChunkError, TTSError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int], None]
StatusCallback = Callable[[str], None]
ParallelismCallback = Callable[[int, int], None]


@dataclass(slots=True, frozen=True)
class _ChunkTask:
    index: int
    text: str
    filename: Path


@dataclass(slots=True)
class _ChunkRequestMeta:
    chunk_index: int
    request_id: str | None
    model_header: str | None
    file: str
    attempts: int
    characters: int
    retry_headers: dict[str, str] | None = None


class _RunCoordinator:
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


class _CombinedCancelEvent:
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


CancelEvent = threading.Event | _CombinedCancelEvent | None


def compute_backoff(e: Exception, attempt: int) -> float:
    try:
        resp = getattr(e, "response", None)
        if resp and getattr(resp, "headers", None):
            retry_after_ms = resp.headers.get("retry-after-ms")
            if retry_after_ms:
                try:
                    return float(retry_after_ms) / 1000.0
                except ValueError:
                    pass
            retry_after = resp.headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
    except Exception:
        pass
    base = max(1.0, float(getattr(settings, "RETRY_DELAY", 5)))
    delay = base * (2**attempt)
    jitter = random.uniform(0, 0.2 * delay)
    return delay + jitter


class TTSService:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or None
        self._base_url = base_url
        self._timeout = timeout
        self._client_local = threading.local()
        self._client: OpenAI | None = None
        self._last_run_coordinator: _RunCoordinator | None = None

    def _build_client(self) -> OpenAI:
        return OpenAI(
            api_key=self._api_key,
            timeout=self._timeout,
            base_url=self._base_url,
            max_retries=0,
        )

    def _get_client(self) -> OpenAI:
        client = getattr(self._client_local, "client", None)
        if client is None:
            client = self._build_client()
            self._client_local.client = client
            if self._client is None:
                self._client = client
        return client

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
        self._ensure_not_cancelled(cancel_event)
        self._validate_options(
            text=text,
            output_path=output_path,
            model=model,
            voice=voice,
            response_format=response_format,
            speed=speed,
        )
        require_preflight()

        normalized_text = text
        chunks = split_text(normalized_text, settings.MAX_CHUNK_SIZE)
        total_chunks = len(chunks)
        if total_chunks == 0:
            raise TTSChunkError("No text chunks generated after splitting.")

        logger.info("Processing %d text chunk(s).", total_chunks)
        if on_progress:
            on_progress(1)

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f"{output_path_obj.stem}_chunks_", dir=output_path_obj.parent)
        )

        temp_files: list[str] = []
        chunk_meta: dict[int, _ChunkRequestMeta] = {}
        meta_lock = threading.Lock()

        tasks = [
            _ChunkTask(
                index=i,
                text=chunk,
                filename=temp_dir / f"chunk_{i:04d}.{response_format}",
            )
            for i, chunk in enumerate(chunks, start=1)
        ]
        temp_files = [str(task.filename) for task in tasks]
        expected_indexes = {task.index for task in tasks}
        effective_parallelism = max(1, min(8, int(parallelism or settings.PARALLELISM)))
        worker_count = min(effective_parallelism, total_chunks)
        abort_event = threading.Event()
        active_cancel_event = _CombinedCancelEvent(cancel_event, abort_event)

        try:
            if total_chunks > 1 and effective_parallelism > 1:
                coordinator = _RunCoordinator(worker_count)
                self._last_run_coordinator = coordinator
                logger.info("Parallel chunk generation enabled: %d", effective_parallelism)
                if on_status:
                    on_status(
                        f"Generating {total_chunks} chunks with parallelism {effective_parallelism}"
                    )
                if on_parallelism:
                    on_parallelism(0, worker_count)
                self._generate_parallel(
                    tasks=tasks,
                    model=model,
                    voice=voice,
                    response_format=response_format,
                    speed=speed,
                    instructions=instructions,
                    chunk_meta=chunk_meta,
                    expected_indexes=expected_indexes,
                    meta_lock=meta_lock,
                    on_progress=on_progress,
                    on_status=on_status,
                    on_parallelism=on_parallelism,
                    cancel_event=active_cancel_event,
                    coordinator=coordinator,
                    abort_event=abort_event,
                )
            else:
                self._last_run_coordinator = None
                if on_parallelism:
                    on_parallelism(0, 1)
                self._generate_serial(
                    tasks=tasks,
                    total_chunks=total_chunks,
                    model=model,
                    voice=voice,
                    response_format=response_format,
                    speed=speed,
                    instructions=instructions,
                    chunk_meta=chunk_meta,
                    expected_indexes=expected_indexes,
                    meta_lock=meta_lock,
                    on_progress=on_progress,
                    on_status=on_status,
                    on_parallelism=on_parallelism,
                    cancel_event=active_cancel_event,
                )

            self._ensure_not_cancelled(active_cancel_event)
            ordered_chunk_meta = self._ordered_chunk_meta(tasks=tasks, chunk_meta=chunk_meta)
            concatenate_audio_files(temp_files, str(output_path_obj))
            if on_progress:
                on_progress(100)
            logger.info("TTS generation complete. Output saved to: %s", output_path_obj)

            ordered_meta = [asdict(item) for item in ordered_chunk_meta]
            sidecar = {
                "app": settings.env_snapshot(),
                "model": model,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
                "instructions_hash": sha256_text(instructions or ""),
                "input_hash": sha256_text(normalized_text),
                "input_chars": len(normalized_text),
                "chunk_count": total_chunks,
                "chunk_size": settings.MAX_CHUNK_SIZE,
                "parallelism_requested": effective_parallelism,
                "parallelism_used": worker_count,
                "retain_files": retain_files,
                "stream_format": getattr(settings, "STREAM_FORMAT", None),
                "chunk_dir": str(temp_dir) if retain_files else None,
                "request_meta": ordered_meta,
            }
            try:
                write_sidecar_metadata(str(output_path_obj), sidecar)
            except Exception as exc:
                logger.warning("Failed to write sidecar metadata: %s", exc)

            message = f"TTS audio saved successfully to:\n{output_path_obj}"
            if retain_files:
                message += f"\nChunk files kept in:\n{temp_dir}"
            return message
        except TTSError as exc:
            if retain_files:
                raise self._with_retained_dir(exc, temp_dir) from exc
            raise
        finally:
            if not retain_files:
                cleanup_files(temp_files)
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _validate_options(
        self,
        *,
        text: str,
        output_path: str,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
    ) -> None:
        if not text or not text.strip():
            raise TTSChunkError("No text provided.")
        if not output_path or not str(output_path).strip():
            raise ConfigError("An output path is required.")
        if model not in settings.TTS_MODELS:
            raise ConfigError(f"Unsupported model: {model}")
        if voice not in settings.TTS_VOICES:
            raise ConfigError(f"Unsupported voice: {voice}")
        if response_format not in settings.TTS_FORMATS:
            raise ConfigError(f"Unsupported response format: {response_format}")
        if not math.isfinite(speed):
            raise ConfigError("Speed must be a finite number.")
        if not (settings.MIN_SPEED <= speed <= settings.MAX_SPEED):
            raise ConfigError(
                f"Speed must be between {settings.MIN_SPEED} and {settings.MAX_SPEED}."
            )

    def _generate_serial(
        self,
        *,
        tasks: list[_ChunkTask],
        total_chunks: int,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        instructions: str,
        chunk_meta: dict[int, _ChunkRequestMeta],
        expected_indexes: set[int],
        meta_lock: threading.Lock,
        on_progress: ProgressCallback | None,
        on_status: StatusCallback | None,
        on_parallelism: ParallelismCallback | None,
        cancel_event: CancelEvent,
    ) -> None:
        for task in tasks:
            self._ensure_not_cancelled(cancel_event)
            logger.info("Processing chunk %d/%d...", task.index, total_chunks)
            if on_status:
                on_status(f"Generating chunk {task.index}/{total_chunks}")
            if on_parallelism:
                on_parallelism(1, 1)
            meta = self._generate_chunk_with_retries(
                task=task,
                model=model,
                voice=voice,
                response_format=response_format,
                speed=speed,
                instructions=instructions,
                on_status=on_status,
                on_parallelism=on_parallelism,
                cancel_event=cancel_event,
            )
            self._record_chunk_meta(
                meta=meta,
                chunk_meta=chunk_meta,
                expected_indexes=expected_indexes,
                meta_lock=meta_lock,
            )
            if on_progress:
                on_progress(int((task.index / total_chunks) * 95))
        if on_parallelism:
            on_parallelism(0, 1)

    def _generate_parallel(
        self,
        *,
        tasks: list[_ChunkTask],
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        instructions: str,
        chunk_meta: dict[int, _ChunkRequestMeta],
        expected_indexes: set[int],
        meta_lock: threading.Lock,
        on_progress: ProgressCallback | None,
        on_status: StatusCallback | None,
        on_parallelism: ParallelismCallback | None,
        cancel_event: CancelEvent,
        coordinator: _RunCoordinator,
        abort_event: threading.Event | None = None,
    ) -> None:
        completed = 0
        futures: dict[Future[_ChunkRequestMeta], _ChunkTask] = {}
        with ThreadPoolExecutor(max_workers=min(coordinator.current_cap, len(tasks))) as executor:
            for task in tasks:
                futures[
                    executor.submit(
                        self._generate_chunk_with_retries,
                        task=task,
                        model=model,
                        voice=voice,
                        response_format=response_format,
                        speed=speed,
                        instructions=instructions,
                        on_status=on_status,
                        on_parallelism=on_parallelism,
                        cancel_event=cancel_event,
                        coordinator=coordinator,
                    )
                ] = task

            try:
                for future in as_completed(futures):
                    self._ensure_not_cancelled(cancel_event)
                    meta = future.result()
                    self._record_chunk_meta(
                        meta=meta,
                        chunk_meta=chunk_meta,
                        expected_indexes=expected_indexes,
                        meta_lock=meta_lock,
                    )
                    completed += 1
                    if on_progress:
                        on_progress(int((completed / len(tasks)) * 95))
            except Exception:
                if abort_event is not None:
                    abort_event.set()
                for future in futures:
                    future.cancel()
                raise

    def _ensure_not_cancelled(self, cancel_event: CancelEvent) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise TTSCancelledError("TTS generation cancelled.")

    def _sleep_with_cancel(
        self,
        wait_time: float,
        cancel_event: CancelEvent,
    ) -> None:
        if cancel_event is None:
            time.sleep(wait_time)
            return
        if cancel_event.wait(wait_time):
            raise TTSCancelledError("TTS generation cancelled.")

    def _extract_response_metadata(
        self, response: object
    ) -> tuple[str | None, str | None, dict[str, str] | None]:
        req_id = getattr(response, "request_id", None)
        model_header = None
        retry_headers = None
        try:
            raw_resp = getattr(response, "response", None) or getattr(
                response, "http_response", None
            )
            headers = getattr(raw_resp, "headers", None)
            if headers:
                req_id = req_id or headers.get("x-request-id")
                model_header = headers.get("openai-model")
                retry_headers = {
                    key: str(value)
                    for key, value in headers.items()
                    if key in {"retry-after-ms", "retry-after"}
                }
                if not retry_headers:
                    retry_headers = None
        except Exception:
            pass
        return req_id, model_header, retry_headers

    def _record_chunk_meta(
        self,
        *,
        meta: _ChunkRequestMeta,
        chunk_meta: dict[int, _ChunkRequestMeta],
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

    def _ordered_chunk_meta(
        self,
        *,
        tasks: list[_ChunkTask],
        chunk_meta: dict[int, _ChunkRequestMeta],
    ) -> list[_ChunkRequestMeta]:
        ordered: list[_ChunkRequestMeta] = []
        missing: list[int] = []
        for task in tasks:
            meta = chunk_meta.get(task.index)
            if meta is None:
                missing.append(task.index)
                continue
            ordered.append(meta)
        if missing:
            raise TTSChunkError(
                "Missing successful chunk result(s) before concat: "
                + ", ".join(str(index) for index in missing)
            )
        return ordered

    def _with_retained_dir(self, exc: TTSError, temp_dir: Path) -> TTSError:
        message = f"{exc}\nPartial chunk files kept in:\n{temp_dir}"
        if isinstance(exc, TTSAPIError):
            return TTSAPIError(message, status_code=exc.status_code, request_id=exc.request_id)
        if isinstance(exc, TTSChunkError):
            return TTSChunkError(message, chunk_index=exc.chunk_index, file_path=exc.file_path)
        if isinstance(exc, TTSCancelledError):
            return TTSCancelledError(message)
        return type(exc)(message)

    def _generate_chunk_with_retries(
        self,
        *,
        task: _ChunkTask,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        instructions: str | None,
        on_status: StatusCallback | None = None,
        on_parallelism: ParallelismCallback | None = None,
        cancel_event: CancelEvent = None,
        coordinator: _RunCoordinator | None = None,
    ) -> _ChunkRequestMeta:
        api_params: dict[str, object] = {
            "model": model,
            "voice": voice,
            "input": task.text,
            "response_format": response_format,
            "speed": speed,
        }
        stream_format = getattr(settings, "STREAM_FORMAT", "audio")
        if stream_format:
            api_params["stream_format"] = stream_format
        if model == settings.GPT_4O_MINI_TTS_MODEL and instructions:
            api_params["instructions"] = instructions

        for attempt in range(1, settings.MAX_RETRIES + 1):
            self._ensure_not_cancelled(cancel_event)
            permit_acquired = False
            try:
                if coordinator is not None:
                    coordinator.acquire(cancel_event)
                    permit_acquired = True
                    if on_parallelism is not None:
                        active_workers, worker_cap = coordinator.snapshot()
                        on_parallelism(active_workers, worker_cap)
                client = cast(Any, self._get_client())
                with client.audio.speech.with_streaming_response.create(**api_params) as response:
                    req_id, model_header, retry_headers = self._extract_response_metadata(response)
                    response.stream_to_file(str(task.filename))
                return _ChunkRequestMeta(
                    chunk_index=task.index,
                    request_id=req_id,
                    model_header=model_header,
                    file=str(task.filename),
                    attempts=attempt,
                    characters=len(task.text),
                    retry_headers=retry_headers,
                )
            except RateLimitError as exc:
                if attempt >= settings.MAX_RETRIES:
                    raise TTSAPIError(
                        f"Rate limit persisted after {attempt} attempts while generating chunk "
                        f"{task.index}.",
                    ) from exc
                wait_time = compute_backoff(exc, attempt - 1)
                if coordinator is not None:
                    coordinator.apply_retry_wait(wait_time, reduce_cap=True)
                    if on_parallelism is not None:
                        active_workers, worker_cap = coordinator.snapshot()
                        on_parallelism(active_workers, worker_cap)
                logger.warning(
                    "Rate limit on chunk %d attempt %d. Retrying in %.2fs...",
                    task.index,
                    attempt,
                    wait_time,
                )
                if on_status:
                    on_status(f"Chunk {task.index}: rate limited; retrying in {wait_time:.1f}s")
                self._sleep_with_cancel(wait_time, cancel_event)
            except (APITimeoutError, APIConnectionError) as exc:
                if attempt >= settings.MAX_RETRIES:
                    raise TTSAPIError(
                        f"Connection issue persisted after {attempt} attempts while generating "
                        f"chunk {task.index}: {exc}"
                    ) from exc
                wait_time = compute_backoff(exc, attempt - 1)
                if coordinator is not None:
                    coordinator.apply_retry_wait(wait_time, reduce_cap=False)
                    if on_parallelism is not None:
                        active_workers, worker_cap = coordinator.snapshot()
                        on_parallelism(active_workers, worker_cap)
                logger.warning(
                    "Timeout/connection issue on chunk %d attempt %d. Retrying in %.2fs...",
                    task.index,
                    attempt,
                    wait_time,
                )
                if on_status:
                    on_status(f"Chunk {task.index}: connection issue; retrying in {wait_time:.1f}s")
                self._sleep_with_cancel(wait_time, cancel_event)
            except APIStatusError as exc:
                status = getattr(exc, "status_code", None)
                req_id = getattr(exc, "request_id", None)
                message = getattr(exc, "message", str(exc))
                if status and status >= 500 and attempt < settings.MAX_RETRIES:
                    wait_time = compute_backoff(exc, attempt - 1)
                    if coordinator is not None:
                        coordinator.apply_retry_wait(wait_time, reduce_cap=False)
                        if on_parallelism is not None:
                            active_workers, worker_cap = coordinator.snapshot()
                            on_parallelism(active_workers, worker_cap)
                    if on_status:
                        on_status(
                            f"Chunk {task.index}: server error {status}; retrying in "
                            f"{wait_time:.1f}s"
                        )
                    self._sleep_with_cancel(wait_time, cancel_event)
                    continue
                detail = f"API Error while generating chunk {task.index}: {message}"
                if status:
                    detail += f" (Status code: {status})"
                if req_id:
                    detail += f" [request id: {req_id}]"
                raise TTSAPIError(detail, status_code=status, request_id=req_id) from exc
            except APIError as exc:
                message = getattr(exc, "message", str(exc))
                raise TTSAPIError(
                    f"OpenAI API Error while generating chunk {task.index}: {message}"
                ) from exc
            except OpenAIError as exc:
                raise TTSAPIError(
                    f"OpenAI Error while generating chunk {task.index}: {exc}"
                ) from exc
            except OSError as exc:
                raise TTSChunkError(
                    f"File saving error for chunk {task.index}: {exc}",
                    chunk_index=task.index,
                    file_path=str(task.filename),
                ) from exc
            finally:
                if permit_acquired and coordinator is not None:
                    coordinator.release()
                    if on_parallelism is not None:
                        active_workers, worker_cap = coordinator.snapshot()
                        on_parallelism(active_workers, worker_cap)

        raise TTSChunkError(
            f"Failed to save chunk {task.index} after {settings.MAX_RETRIES} attempts.",
            chunk_index=task.index,
            file_path=str(task.filename),
        )
