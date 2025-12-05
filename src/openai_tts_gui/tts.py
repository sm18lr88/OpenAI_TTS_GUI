import logging
import os
import random
import subprocess
import sys
import time
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
from PyQt6.QtCore import QThread, pyqtSignal

from . import config
from .utils import (
    cleanup_files,
    concatenate_audio_files,
    sha256_text,
    split_text,
    write_sidecar_metadata,
)

logger = logging.getLogger(__name__)


class TTSProcessor(QThread):
    """
    Handles the TTS generation process in a separate thread.
    Emits signals for progress updates, completion, or errors.
    """

    progress_updated = pyqtSignal(int)  # Percentage (0-100)
    tts_complete = pyqtSignal(str)  # Success message
    tts_error = pyqtSignal(str)  # Error message
    status_update = pyqtSignal(str)  # Status / retry info

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self.params = params
        self.temp_files = []
        self.client = None  # Initialize OpenAI client later

    def run(self):
        """The main execution method for the thread."""
        logger.info("TTSProcessor thread started.")
        try:
            # Initialize client here with timeout and optional base URL
            # Timeout docs: https://pypi.org/project/openai/ (Timeouts section)
            api_key_param = str(self.params.get("api_key") or "")
            timeout_value = float(getattr(config, "OPENAI_TIMEOUT", 60.0))
            base_url_value = (
                config.OPENAI_BASE_URL if getattr(config, "OPENAI_BASE_URL", None) else None
            )
            self.client = OpenAI(
                api_key=api_key_param or None,
                timeout=timeout_value,
                base_url=base_url_value,
            )

            text = self.params["text"]
            output_path = self.params["output_path"]
            model = self.params["model"]
            voice = self.params["voice"]
            response_format = self.params["response_format"]
            speed = self.params["speed"]
            instructions = self.params["instructions"]
            retain_files = self.params["retain_files"]

            # Split text into manageable chunks
            chunks = split_text(text, config.MAX_CHUNK_SIZE)
            total_chunks = len(chunks)
            if total_chunks == 0:
                raise ValueError("No text chunks generated after splitting.")

            logger.info(f"Processing {total_chunks} text chunks.")
            self.progress_updated.emit(1)  # Indicate start

            # Ensure output directory exists for chunk files & final output
            output_dir = os.path.dirname(output_path) or "."
            os.makedirs(output_dir, exist_ok=True)
            base_filename = os.path.splitext(os.path.basename(output_path))[0]

            # Process each chunk
            chunk_meta = []
            if getattr(config, "PARALLELISM", 1) > 1:
                logger.info("Parallel chunk generation enabled: %d", config.PARALLELISM)
                files_by_idx = {}
                for i, chunk in enumerate(chunks, start=1):
                    temp_filename = os.path.join(
                        output_dir, f"{base_filename}_chunk_{i}.{response_format}"
                    )
                    self.temp_files.append(temp_filename)
                    files_by_idx[i] = (chunk, temp_filename)
                completed = 0
                with ThreadPoolExecutor(max_workers=config.PARALLELISM) as ex:
                    fut_map = {
                        ex.submit(
                            self._save_chunk_with_retries,
                            chunk,
                            fname,
                            model,
                            voice,
                            response_format,
                            speed,
                            instructions,
                            chunk_meta,
                        ): i
                        for i, (chunk, fname) in files_by_idx.items()
                    }
                    for fut in as_completed(fut_map):
                        ok = fut.result()
                        if not ok:
                            return
                        completed += 1
                        self.progress_updated.emit(int((completed / total_chunks) * 95))
            else:
                for i, chunk in enumerate(chunks, start=1):
                    chunk_start_time = time.time()
                    logger.info(f"Processing chunk {i}/{total_chunks}...")
                    temp_filename = os.path.join(
                        output_dir, f"{base_filename}_chunk_{i}.{response_format}"
                    )
                    self.temp_files.append(temp_filename)
                    success = self._save_chunk_with_retries(
                        chunk,
                        temp_filename,
                        model,
                        voice,
                        response_format,
                        speed,
                        instructions,
                        chunk_meta,
                    )
                    if not success:
                        return
                    chunk_duration = time.time() - chunk_start_time
                    logger.info("Chunk %d processed in %.2f seconds.", i, chunk_duration)
                    self.progress_updated.emit(int((i / total_chunks) * 95))

            # Concatenate audio files
            logger.info("Concatenating audio chunks...")
            concatenate_audio_files(self.temp_files, output_path)
            self.progress_updated.emit(100)  # Signal completion
            logger.info(f"TTS generation complete. Output saved to: {output_path}")
            # Sidecar metadata for reproducibility
            sidecar = {
                "app": config.env_snapshot(),
                "model": model,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
                "instructions_hash": sha256_text(instructions or ""),
                "chunk_size": config.MAX_CHUNK_SIZE,
                "retain_files": retain_files,
                "stream_format": getattr(config, "STREAM_FORMAT", None),
                "request_meta": chunk_meta,
            }
            try:
                write_sidecar_metadata(output_path, sidecar)
            except Exception as se:
                logger.warning(f"Failed to write sidecar metadata: {se}")
            self.tts_complete.emit(f"TTS audio saved successfully to:\n{output_path}")

        except (
            OSError,
            ValueError,
            FileNotFoundError,
            subprocess.CalledProcessError,
        ) as e:  # <--- Error was caught here
            logger.exception(f"Error during TTS processing setup or concatenation: {e}")
            self.tts_error.emit(f"Processing failed: {e}")
        except OpenAIError as e:
            # This catches API related errors not handled by retry loop (e.g., auth, config)
            logger.exception(f"OpenAI API error during processing: {e}")
            self.tts_error.emit(f"OpenAI API Error: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred in TTSProcessor: {e}")
            self.tts_error.emit(f"An unexpected error occurred: {e}")
        finally:
            # Cleanup temporary files if needed, regardless of success/error
            if not self.params.get("retain_files", False):
                cleanup_files(self.temp_files)
            logger.info("TTSProcessor thread finished.")

    def _save_chunk_with_retries(
        self,
        text_chunk: str,
        filename: str,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        instructions: str | None,
        chunk_meta_accum: list,
    ) -> bool:
        """Attempts to generate and save a single TTS chunk with retries."""
        logger.info(f"Attempting to generate audio for chunk, saving to {filename}")

        if self.client is None:
            self.tts_error.emit("OpenAI client not initialized.")
            return False

        # Prepare API call parameters
        api_params = {
            "model": model,
            "voice": voice,
            "input": text_chunk,
            "response_format": response_format,
            "speed": speed,
        }
        stream_format = getattr(config, "STREAM_FORMAT", "audio")
        if stream_format:
            api_params["stream_format"] = stream_format
        # Only include instructions if the model supports it and they are provided
        if model == config.GPT_4O_MINI_TTS_MODEL and instructions:
            api_params["instructions"] = instructions

        for attempt in range(config.MAX_RETRIES):
            try:
                logger.debug(
                    "API call attempt %d/%d for %s",
                    attempt + 1,
                    config.MAX_RETRIES,
                    os.path.basename(filename),
                )
                start_time = time.time()

                # Prefer streaming-to-file for better memory behavior
                with self.client.audio.speech.with_streaming_response.create(
                    **api_params
                ) as response:
                    # extract headers / ids if available
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
                    chunk_meta_accum.append(
                        {"request_id": req_id, "model_header": model_hdr, "file": filename}
                    )

                api_call_duration = time.time() - start_time
                logger.debug(f"API call successful in {api_call_duration:.2f} seconds.")

                logger.info(f"Successfully saved chunk to {filename}")
                return True

            except RateLimitError as e:
                wait_time = _compute_backoff(e, attempt)
                logger.warning(
                    "Rate limit on attempt %d. Retrying in %.2fs... Error: %s",
                    attempt + 1,
                    wait_time,
                    e,
                )
                self.status_update.emit(f"Rate limit; retrying in {wait_time:.1f}s")
                time.sleep(wait_time)  # Wait before retrying

            except (APITimeoutError, APIConnectionError) as e:
                wait_time = _compute_backoff(e, attempt)
                logger.warning(
                    "Timeout/connection issue on attempt %d. Retrying in %.2fs... Error: %s",
                    attempt + 1,
                    wait_time,
                    e,
                )
                self.status_update.emit(f"Connection issue; retrying in {wait_time:.1f}s")
                time.sleep(wait_time)

            except APIStatusError as e:
                status = getattr(e, "status_code", None)
                req_id = getattr(e, "request_id", None)
                message = getattr(e, "message", str(e))
                logger.error(
                    "OpenAI API status error on attempt %d: %s %s (request id: %s)",
                    attempt + 1,
                    status,
                    message,
                    req_id,
                )
                # Decide if retryable. 5xx errors might be, 4xx usually not.
                if status and status >= 500 and attempt < config.MAX_RETRIES - 1:
                    wait_time = _compute_backoff(e, attempt)
                    logger.warning(
                        "Server error likely transient. Retrying in %.2fs (request id: %s)...",
                        wait_time,
                        req_id,
                    )
                    self.status_update.emit(
                        f"Server error {status}; retrying in {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                else:
                    detail = f"API Error: {message}"
                    if status:
                        detail += f" (Status code: {status})"
                    if req_id:
                        detail += f" [request id: {req_id}]"
                    self.tts_error.emit(detail)
                    return False  # Non-retryable or final attempt failed

            except APIError as e:
                # Catch other specific API errors (e.g., malformed responses)
                message = getattr(e, "message", str(e))
                logger.error("OpenAI API error on attempt %d: %s", attempt + 1, message)
                self.tts_error.emit(f"OpenAI API Error: {message}")
                return False

            except OpenAIError as e:  # Catch broader OpenAI errors
                logger.error(f"General OpenAI error on attempt {attempt + 1}: {e}")
                # These might indicate config issues, not usually retryable
                self.tts_error.emit(f"OpenAI Error: {e}")
                return False

            except OSError as e:
                logger.exception(
                    f"File I/O error saving chunk {filename} on attempt {attempt+1}: {e}"
                )
                self.tts_error.emit(f"File saving error: {e}")
                return False  # Likely permissions or disk space issue, don't retry

            except Exception as e:
                # Catch unexpected errors during the process
                logger.exception(
                    f"Unexpected error saving chunk {filename} on attempt {attempt + 1}: {e}"
                )
                self.tts_error.emit(f"Unexpected error: {e}")
                return False  # Unexpected error, stop processing

        # If loop finishes without returning True, all retries failed
        logger.error(f"Failed to save chunk {filename} after {config.MAX_RETRIES} attempts.")
        self.tts_error.emit(
            "Failed to generate audio chunk after multiple retries. See logs for details."
        )
        return False


def _compute_backoff(e: Exception, attempt: int) -> float:
    """Exponential backoff with jitter and Retry-After honor when available."""
    # Retry-After (seconds) if provided
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
    base = max(1.0, float(getattr(config, "RETRY_DELAY", 5)))
    # exponential: base * 2^attempt plus jitter up to 20% of that
    delay = base * (2**attempt)
    jitter = random.uniform(0, 0.2 * delay)
    return delay + jitter


if __name__ == "__main__":
    # Simple CLI passthrough (kept minimal; use cli.py entry point for full CLI)
    import argparse

    from .utils import read_api_key

    parser = argparse.ArgumentParser(description="OpenAI TTS (module mode)")
    parser.add_argument("--in", dest="infile", required=True, help="Input text file")
    parser.add_argument("--out", dest="outfile", required=True, help="Output audio path")
    parser.add_argument("--model", default="tts-1")
    parser.add_argument("--voice", default="alloy")
    parser.add_argument("--format", default="mp3")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--instructions", default="")
    args = parser.parse_args()

    api_key = read_api_key()
    if not api_key:
        print("Missing OPENAI API key.", file=sys.stderr)
        sys.exit(1)
    with open(args.infile, encoding="utf-8") as f:
        text = f.read()
    params = {
        "api_key": api_key,
        "text": text,
        "output_path": args.outfile,
        "model": args.model,
        "voice": args.voice,
        "response_format": args.format,
        "speed": float(args.speed),
        "instructions": args.instructions,
        "retain_files": False,
    }
    # Run in the current thread (synchronous) using same helpers
    tp = TTSProcessor(params)
    tp.run()
