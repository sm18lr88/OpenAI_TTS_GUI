from __future__ import annotations

import pytest

from openai_tts_gui import config
from openai_tts_gui.config import settings
from openai_tts_gui.errors import TTSAPIError
from openai_tts_gui.tts import TTSService, compute_backoff
from tests.fakes_tts_service import (
    FakeAPIStatusError,
    FakeChunkOutcome,
    FakeRateLimitError,
    FakeTTSServiceHarness,
)
from tests.tts_rate_limit_support import patch_rate_limit_generation_seams


def test_fake_provider_failure_shape():
    # Given: a fake provider scripted to return a rate-limit response.
    harness = FakeTTSServiceHarness(
        {
            "chunk-a": [
                FakeChunkOutcome(
                    error=FakeRateLimitError(
                        "retry later",
                        headers={
                            "retry-after-ms": "2500",
                            "retry-after": "3",
                            "x-request-id": "req-rate-limit",
                        },
                        request_id="req-rate-limit",
                    )
                )
            ]
        }
    )
    client = harness.openai_class()(api_key="sk-test")

    # When: the streaming response is created.
    with (
        pytest.raises(FakeRateLimitError) as exc_info,
        client.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice="alloy",
            input="chunk-a",
            response_format="wav",
            speed=1.0,
            stream_format="audio",
        ),
    ):
        pass

    # Then: the provider call shape, response metadata, and event sequence are retained.
    assert harness.client_kwargs == [{"api_key": "sk-test"}]
    assert harness.api_calls == [
        {
            "attempt": 1,
            "api_params": {
                "model": "tts-1",
                "voice": "alloy",
                "input": "chunk-a",
                "response_format": "wav",
                "speed": 1.0,
                "stream_format": "audio",
            },
            "thread_name": harness.api_calls[0]["thread_name"],
        }
    ]
    error = exc_info.value
    assert error.request_id == "req-rate-limit"
    assert error.response.headers["retry-after-ms"] == "2500"
    assert error.response.headers["retry-after"] == "3"
    assert error.response.headers["x-request-id"] == "req-rate-limit"
    assert [event.kind for event in harness.events] == ["create", "enter", "raise"]


def test_service_disables_sdk_retries_for_tts_client(monkeypatch):
    # Given: a fake OpenAI client constructor that records its arguments.
    captured_kwargs = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", FakeOpenAI)
    service = TTSService(api_key="sk-test")

    # When: the service creates its client.
    service._build_client()

    # Then: SDK retries remain disabled while configured connection values are retained.
    assert captured_kwargs["api_key"] == "sk-test"
    assert captured_kwargs["timeout"] == getattr(settings, "OPENAI_TIMEOUT", 60.0)
    assert captured_kwargs["base_url"] is None
    assert captured_kwargs["max_retries"] == 0


def test_retry_after_ms_header_overrides_retry_after_and_backoff(monkeypatch):
    # Given: deterministic retry jitter.
    monkeypatch.setattr("openai_tts_gui.tts._service.random.uniform", lambda *_args: 0.0)

    # When: retry timing is computed from provider headers and fallback settings.
    assert (
        compute_backoff(
            FakeRateLimitError(headers={"retry-after-ms": "2500", "retry-after": "7"}),
            2,
        )
        == 2.5
    )
    assert compute_backoff(FakeRateLimitError(headers={"retry-after": "3"}), 2) == 3.0

    # Then: milliseconds take precedence and the fallback remains exponential.
    base = max(1.0, float(getattr(config, "RETRY_DELAY", 5)))
    assert compute_backoff(FakeRateLimitError(headers={}), 2) == base * 4


def test_non_retryable_401_fails_without_sleep(monkeypatch, tmp_path):
    # Given: a single chunk that receives a non-retryable authentication failure.
    output = tmp_path / "auth-fail.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-a": [
                FakeChunkOutcome(
                    error=FakeAPIStatusError("auth error", status_code=401, request_id="auth-1")
                )
            ]
        }
    )
    sleeps: list[float] = []
    patch_rate_limit_generation_seams(monkeypatch, harness, concat_calls)
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda *_args: ["chunk-a"])
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)
    service = TTSService(api_key="sk-test")
    monkeypatch.setattr(
        service, "_sleep_with_cancel", lambda wait_time, _cancel_event: sleeps.append(wait_time)
    )

    # When: generation receives the authentication failure.
    with pytest.raises(TTSAPIError) as exc_info:
        service.generate(
            text="ignored because split_text is patched",
            output_path=str(output),
            model="tts-1",
            voice="alloy",
            response_format="wav",
            speed=1.0,
            instructions="",
            retain_files=False,
        )

    # Then: generation fails without retrying, concatenating, or writing output.
    assert "Status code: 401" in str(exc_info.value)
    assert sleeps == []
    assert concat_calls == []
    assert not output.exists()
