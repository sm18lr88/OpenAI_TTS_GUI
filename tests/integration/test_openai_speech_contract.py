from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import RemoteProtocolError
from openai import InternalServerError, OpenAI, RateLimitError

from tests.integration.speech_server import ResponseKind, SpeechResponse, SpeechServer

pytestmark = pytest.mark.integration

_SYNTHETIC_API_KEY = "sk-loopback-synthetic"


def _stream_audio(client: OpenAI, output: Path) -> None:
    with client.audio.speech.with_streaming_response.create(
        model="tts-1", voice="alloy", input="loopback speech", response_format="wav"
    ) as response:
        response.stream_to_file(output)


def test_sdk_streams_audio_when_loopback_contract_server_is_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with SpeechServer() as server:
        monkeypatch.setenv("OPENAI_BASE_URL", server.base_url)
        with OpenAI(api_key=_SYNTHETIC_API_KEY, max_retries=0) as client:
            output = tmp_path / "speech.wav"
            _stream_audio(client, output)

        request = server.requests[0]
        assert output.read_bytes() == b"loopback-audio"
        assert request.destination == server.base_url
        assert request.authorization_present is True
        assert json.loads(request.body)["input"] == "loopback speech"


def test_sdk_response_close_releases_blocked_handler_without_server_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SpeechServer((SpeechResponse(ResponseKind.BLOCKED_AUDIO),)) as server:
        monkeypatch.setenv("OPENAI_BASE_URL", server.base_url)
        with OpenAI(api_key=_SYNTHETIC_API_KEY, max_retries=0) as client:
            with client.audio.speech.with_streaming_response.create(
                model="tts-1", voice="alloy", input="close stream", response_format="wav"
            ):
                assert server.wait_until_blocked()
            assert server.wait_until_client_closed()
            assert server.is_running


def test_sdk_surfaces_retry_and_server_headers_without_sdk_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = (
        SpeechResponse(ResponseKind.RATE_LIMIT, request_id="req-429"),
        SpeechResponse(ResponseKind.SERVER_ERROR, request_id="req-500"),
    )
    with SpeechServer(responses) as server:
        monkeypatch.setenv("OPENAI_BASE_URL", server.base_url)
        with OpenAI(api_key=_SYNTHETIC_API_KEY, max_retries=0) as client:
            with pytest.raises(RateLimitError) as rate_limit:
                _stream_audio(client, tmp_path / "rate.wav")
            with pytest.raises(InternalServerError) as server_error:
                _stream_audio(client, tmp_path / "server.wav")

    assert rate_limit.value.response.headers["retry-after-ms"] == "1"
    assert server_error.value.request_id == "req-500"
    assert [record.status for record in server.responses_sent] == [429, 500]


def test_sdk_reports_mid_body_close_and_empty_success_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = (
        SpeechResponse(ResponseKind.PARTIAL_CLOSE, b"partial-audio", "req-close"),
        SpeechResponse(ResponseKind.EMPTY_BODY, request_id="req-empty"),
    )
    with SpeechServer(responses) as server:
        monkeypatch.setenv("OPENAI_BASE_URL", server.base_url)
        with OpenAI(api_key=_SYNTHETIC_API_KEY, max_retries=0) as client:
            with pytest.raises(RemoteProtocolError):
                _stream_audio(client, tmp_path / "partial.wav")
            _stream_audio(client, tmp_path / "empty.wav")

    assert (tmp_path / "empty.wav").read_bytes() == b""
    assert [record.kind for record in server.responses_sent] == [
        ResponseKind.PARTIAL_CLOSE,
        ResponseKind.EMPTY_BODY,
    ]
