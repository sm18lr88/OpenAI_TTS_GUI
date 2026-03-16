import logging
import os
import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from ..config import settings
from ..core.audio import cleanup_files, concatenate_audio_files
from ..core.metadata import sha256_text, write_sidecar_metadata
from ..core.text import split_text
from ..errors import TTSAPIError, TTSChunkError

logger = logging.getLogger(__name__)


def compute_backoff(e: Exception, attempt: int) -> float:
    try:
        resp = getattr(e, "response", None)
        if resp and getattr(resp, "headers", None):
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    return float(ra)
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
    ):
        self._client = OpenAI(
            api_key=api_key or None,
            timeout=timeout,
            base_url=base_url,
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
        retain_files: bool = False,
        on_progress: Callable[[int], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        if not text or not text.strip():
            raise TTSChunkError("No text provided.")
        chunks = split_text(text, settings.MAX_CHUNK_SIZE)
        total_chunks = len(chunks)
        if total_chunks == 0:
            raise TTSChunkError("No text chunks generated after splitting.")

        logger.info(f"Processing {total_chunks} text chunks.")
        if on_progress:
            on_progress(1)

        output_dir = os.path.dirname(output_path) or "."
        os.makedirs(output_dir, exist_ok=True)
        base_filename = os.path.splitext(os.path.basename(output_path))[0]

        temp_files: list[str] = []
        chunk_meta: list[dict] = []
        meta_lock = threading.Lock()

        try:
            if getattr(settings, "PARALLELISM", 1) > 1:
                logger.info("Parallel chunk generation enabled: %d", settings.PARALLELISM)
                files_by_idx: dict[int, tuple[str, str]] = {}
                for i, chunk in enumerate(chunks, start=1):
                    temp_filename = os.path.join(
                        output_dir, f"{base_filename}_chunk_{i}.{response_format}"
                    )
                    temp_files.append(temp_filename)
                    files_by_idx[i] = (chunk, temp_filename)
                completed = 0
                with ThreadPoolExecutor(max_workers=settings.PARALLELISM) as ex:
                    fut_map = {
                        ex.submit(
                            self._generate_chunk_with_retries,
                            chunk,
                            fname,
                            model,
                            voice,
                            response_format,
                            speed,
                            instructions,
                            chunk_meta,
                            meta_lock,
                            on_status,
                        ): i
                        for i, (chunk, fname) in files_by_idx.items()
                    }
                    for fut in as_completed(fut_map):
                        fut.result()
                        completed += 1
                        if on_progress:
                            on_progress(int((completed / total_chunks) * 95))
            else:
                for i, chunk in enumerate(chunks, start=1):
                    logger.info(f"Processing chunk {i}/{total_chunks}...")
                    temp_filename = os.path.join(
                        output_dir, f"{base_filename}_chunk_{i}.{response_format}"
                    )
                    temp_files.append(temp_filename)
                    self._generate_chunk_with_retries(
                        chunk,
                        temp_filename,
                        model,
                        voice,
                        response_format,
                        speed,
                        instructions,
                        chunk_meta,
                        meta_lock,
                        on_status,
                    )
                    if on_progress:
                        on_progress(int((i / total_chunks) * 95))

            concatenate_audio_files(temp_files, output_path)
            if on_progress:
                on_progress(100)
            logger.info(f"TTS generation complete. Output saved to: {output_path}")

            sidecar = {
                "app": settings.env_snapshot(),
                "model": model,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
                "instructions_hash": sha256_text(instructions or ""),
                "chunk_size": settings.MAX_CHUNK_SIZE,
                "retain_files": retain_files,
                "stream_format": getattr(settings, "STREAM_FORMAT", None),
                "request_meta": chunk_meta,
            }
            try:
                write_sidecar_metadata(output_path, sidecar)
            except Exception as se:
                logger.warning(f"Failed to write sidecar metadata: {se}")

            return f"TTS audio saved successfully to:\n{output_path}"
        finally:
            if not retain_files:
                cleanup_files(temp_files)

    def _generate_chunk_with_retries(
        self,
        text_chunk: str,
        filename: str,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        instructions: str | None,
        chunk_meta_accum: list,
        meta_lock: threading.Lock,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        api_params: dict = {
            "model": model,
            "voice": voice,
            "input": text_chunk,
            "response_format": response_format,
            "speed": speed,
        }
        stream_format = getattr(settings, "STREAM_FORMAT", "audio")
        if stream_format:
            api_params["stream_format"] = stream_format
        if model == settings.GPT_4O_MINI_TTS_MODEL and instructions:
            api_params["instructions"] = instructions

        for attempt in range(settings.MAX_RETRIES):
            try:
                with self._client.audio.speech.with_streaming_response.create(
                    **api_params
                ) as response:
                    req_id = getattr(response, "request_id", None)
                    model_hdr = None
                    try:
                        raw_resp = getattr(response, "response", None) or getattr(
                            response, "http_response", None
                        )
                        if raw_resp and getattr(raw_resp, "headers", None):
                            req_id = req_id or raw_resp.headers.get("x-request-id")
                            model_hdr = raw_resp.headers.get("openai-model")
                    except Exception:
                        pass
                    response.stream_to_file(filename)
                if req_id or model_hdr:
                    with meta_lock:
                        chunk_meta_accum.append(
                            {"request_id": req_id, "model_header": model_hdr, "file": filename}
                        )
                return

            except RateLimitError as e:
                wait_time = compute_backoff(e, attempt)
                logger.warning(
                    "Rate limit on attempt %d. Retrying in %.2fs...", attempt + 1, wait_time
                )
                if on_status:
                    on_status(f"Rate limit; retrying in {wait_time:.1f}s")
                time.sleep(wait_time)

            except (APITimeoutError, APIConnectionError) as e:
                wait_time = compute_backoff(e, attempt)
                logger.warning(
                    "Timeout/connection issue on attempt %d. Retrying in %.2fs...",
                    attempt + 1,
                    wait_time,
                )
                if on_status:
                    on_status(f"Connection issue; retrying in {wait_time:.1f}s")
                time.sleep(wait_time)

            except APIStatusError as e:
                status = getattr(e, "status_code", None)
                req_id = getattr(e, "request_id", None)
                message = getattr(e, "message", str(e))
                if status and status >= 500 and attempt < settings.MAX_RETRIES - 1:
                    wait_time = compute_backoff(e, attempt)
                    if on_status:
                        on_status(f"Server error {status}; retrying in {wait_time:.1f}s")
                    time.sleep(wait_time)
                else:
                    detail = f"API Error: {message}"
                    if status:
                        detail += f" (Status code: {status})"
                    if req_id:
                        detail += f" [request id: {req_id}]"
                    raise TTSAPIError(detail, status_code=status, request_id=req_id) from e

            except APIError as e:
                message = getattr(e, "message", str(e))
                raise TTSAPIError(f"OpenAI API Error: {message}") from e

            except OpenAIError as e:
                raise TTSAPIError(f"OpenAI Error: {e}") from e

            except OSError as e:
                raise TTSChunkError(f"File saving error: {e}", file_path=filename) from e

        raise TTSChunkError(
            f"Failed to save chunk {filename} after {settings.MAX_RETRIES} attempts.",
            file_path=filename,
        )
