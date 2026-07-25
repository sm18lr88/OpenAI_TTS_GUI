# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["openai>=2.9,<3"]
# ///
from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from httpx import RemoteProtocolError
from openai import InternalServerError, OpenAI, RateLimitError

from tests.integration.speech_server import ResponseKind, SpeechResponse, SpeechServer

_SYNTHETIC_API_KEY = "sk-loopback-synthetic"
_EVIDENCE_PATH = Path(".omo/evidence/task-4-openai-tts-codebase-modernization-requests.json")
_COMMAND_LOG_PATH = Path(".omo/evidence/task-4-openai-tts-codebase-modernization-command-log.txt")


def _stream_audio(client: OpenAI, output: Path) -> None:
    with client.audio.speech.with_streaming_response.create(
        model="tts-1", voice="alloy", input="loopback speech", response_format="wav"
    ) as response:
        response.stream_to_file(output)


def _expect_error(error_type: type[Exception], action: Callable[[], None]) -> None:
    try:
        action()
    except error_type:
        return
    raise AssertionError(f"Expected {error_type.__name__}")


def main() -> None:
    responses = (
        SpeechResponse(ResponseKind.AUDIO, b"manual-audio", "req-audio"),
        SpeechResponse(ResponseKind.RATE_LIMIT, request_id="req-429"),
        SpeechResponse(ResponseKind.SERVER_ERROR, request_id="req-500"),
        SpeechResponse(ResponseKind.PARTIAL_CLOSE, b"manual-partial", "req-close"),
        SpeechResponse(ResponseKind.BLOCKED_AUDIO, b"manual-release", "req-release"),
        SpeechResponse(ResponseKind.EMPTY_BODY, request_id="req-empty"),
    )
    server = SpeechServer(responses)
    with tempfile.TemporaryDirectory(dir=".pytest_tmp") as temporary_directory:
        output_directory = Path(temporary_directory)
        with server:
            os.environ["OPENAI_BASE_URL"] = server.base_url
            with OpenAI(api_key=_SYNTHETIC_API_KEY, max_retries=0) as client:
                _stream_audio(client, output_directory / "audio.wav")
                _expect_error(
                    RateLimitError, lambda: _stream_audio(client, output_directory / "rate.wav")
                )
                _expect_error(
                    InternalServerError,
                    lambda: _stream_audio(client, output_directory / "server.wav"),
                )
                _expect_error(
                    RemoteProtocolError,
                    lambda: _stream_audio(client, output_directory / "partial.wav"),
                )
                with client.audio.speech.with_streaming_response.create(
                    model="tts-1", voice="alloy", input="close stream", response_format="wav"
                ):
                    assert server.wait_until_blocked()
                assert server.wait_until_client_closed()
                _stream_audio(client, output_directory / "empty.wav")

    server.write_transcript(_EVIDENCE_PATH)
    transcript = _EVIDENCE_PATH.read_text(encoding="utf-8")
    assert "Bearer" not in transcript
    _COMMAND_LOG_PATH.write_text(
        "uv run --python 3.14 python -m tests.integration.write_task4_evidence\n"
        "manual loopback SDK contract: PASS\n"
        "destination: 127.0.0.1 only; authorization values: omitted\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
