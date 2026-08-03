from __future__ import annotations

import threading
from collections.abc import Callable
from typing import NamedTuple, Protocol

from httpx import HTTPError, StreamClosed

from .. import config
from ..errors import ContractError
from ._contracts import CancellationStage, ProviderReceipt, ProviderRequest
from ._run_state import AttemptKey, RunState


class OpenAISymbols(NamedTuple):
    connection_error: type[Exception]
    api_error: type[Exception]
    status_error: type[Exception]
    timeout_error: type[Exception]
    client_type: type
    openai_error: type[Exception]
    rate_limit_error: type[Exception]


def load_openai_symbols() -> OpenAISymbols:
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
    except ImportError as _openai_import_error:
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

        class OpenAI:
            def __init__(self, *args, **kwargs) -> None:
                raise ModuleNotFoundError(
                    "TTSService requires the 'openai' package."
                ) from _OPENAI_IMPORT_ERROR

    return OpenAISymbols(
        APIConnectionError,
        APIError,
        APIStatusError,
        APITimeoutError,
        OpenAI,
        OpenAIError,
        RateLimitError,
    )


class ResponseMetadata(NamedTuple):
    request_id: str | None
    model_header: str | None
    retry_headers: dict[str, str] | None


class ProviderStreamError(Exception):
    def __init__(self, message: str, request_id: str | None) -> None:
        self.request_id = request_id
        super().__init__(message)


class StreamingResponse(Protocol):
    def stream_to_file(self, filename: str) -> None: ...

    def close(self) -> None: ...


class StreamingContext(Protocol):
    def __enter__(self) -> StreamingResponse: ...

    def __exit__(self, exception_type, exception, traceback) -> bool: ...


class StreamingRequests(Protocol):
    def create(self, **api_params: str | int | float) -> StreamingContext: ...


class StreamingSpeech(Protocol):
    with_streaming_response: StreamingRequests


class StreamingAudio(Protocol):
    speech: StreamingSpeech


class StreamingClient(Protocol):
    audio: StreamingAudio


class SpeechProvider(Protocol):
    def stream(
        self,
        request: ProviderRequest,
        on_stage: Callable[[CancellationStage], None] | None = None,
        state: RunState | None = None,
        key: AttemptKey | None = None,
    ) -> ProviderReceipt: ...


class ThreadLocalClient:
    def __init__(self, local: threading.local, client_factory) -> None:
        self._local = local
        self._client_factory = client_factory

    def get_client(self):
        client = getattr(self._local, "client", None)
        if client is None:
            client = self._client_factory()
            self._local.client = client
        return client


class OpenAIProviderAdapter:
    def __init__(self, client_factory: Callable[[], StreamingClient]) -> None:
        self._client_factory = client_factory

    def stream(
        self,
        request: ProviderRequest,
        on_stage: Callable[[CancellationStage], None] | None = None,
        state: RunState | None = None,
        key: AttemptKey | None = None,
    ) -> ProviderReceipt:
        params: dict[str, str | float] = {
            "model": request.config.model,
            "voice": request.config.voice,
            "input": request.text,
            "response_format": request.config.response_format,
            "speed": request.config.speed,
        }
        if config.settings.STREAM_FORMAT:
            params["stream_format"] = config.settings.STREAM_FORMAT
        if (
            request.config.model == config.settings.GPT_4O_MINI_TTS_MODEL
            and request.config.instructions
        ):
            params["instructions"] = request.config.instructions
        streaming = self._client_factory().audio.speech.with_streaming_response
        if state is not None:
            if key is None:
                raise ContractError("Provider calls owned by a run require an attempt key.")
            if not state.begin_attempt(key):
                from ..errors import TTSCancelledError

                raise TTSCancelledError("TTS generation cancelled.")
        elif on_stage is not None:
            on_stage(CancellationStage.AWAITING_PROVIDER_RESPONSE)
        with streaming.create(**params) as response:
            metadata = extract_response_metadata(response)
            if state is not None:
                if key is None:
                    raise ContractError("Provider calls owned by a run require an attempt key.")
                if not state.register_response(key, response):
                    response.close()
                    state.complete_attempt(key)
                    from ..errors import TTSCancelledError

                    raise TTSCancelledError("TTS generation cancelled.")
            elif on_stage is not None:
                on_stage(CancellationStage.DURING_PROVIDER_STREAM)
            try:
                response.stream_to_file(request.output_path)
            except (HTTPError, StreamClosed) as exc:
                raise ProviderStreamError(str(exc), metadata.request_id) from exc
        if state is not None:
            if key is None:
                raise ContractError("Provider calls owned by a run require an attempt key.")
            from pathlib import Path

            output_path = Path(request.output_path)
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise OSError("The provider response did not create a non-empty audio file.")
            state.validate_result(key)
        headers = tuple(sorted((metadata.retry_headers or {}).items()))
        return ProviderReceipt(metadata.request_id, metadata.model_header, headers)


def stream_chunk(
    client: StreamingClient, api_params: dict[str, str | int | float], filename: str
) -> ResponseMetadata:
    with client.audio.speech.with_streaming_response.create(**api_params) as response:
        metadata = extract_response_metadata(response)
        response.stream_to_file(filename)
    return metadata


def extract_response_metadata(response) -> ResponseMetadata:
    request_id = getattr(response, "request_id", None)
    model_header = None
    retry_headers = None
    try:
        raw_response = getattr(response, "response", None) or getattr(
            response, "http_response", None
        )
        headers = getattr(raw_response, "headers", None)
        if headers:
            request_id = request_id or headers.get("x-request-id")
            model_header = headers.get("openai-model")
            retry_headers = {
                key: str(value)
                for key, value in headers.items()
                if key in {"retry-after-ms", "retry-after"}
            }
            if not retry_headers:
                retry_headers = None
    except (AttributeError, OSError):
        retry_headers = None
    return ResponseMetadata(request_id, model_header, retry_headers)
