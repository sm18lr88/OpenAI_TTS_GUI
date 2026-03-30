from __future__ import annotations

from pathlib import Path

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


def _patch_basic_generate(monkeypatch, harness, concat_calls):
    def fake_concat(files: list[str], output_path: str) -> None:
        concat_calls.append(list(files))
        Path(output_path).write_bytes(b"joined-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fake_concat)


def test_fake_provider_failure_shape():
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
    captured_kwargs = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", FakeOpenAI)

    service = TTSService(api_key="sk-test")
    service._build_client()

    assert captured_kwargs["api_key"] == "sk-test"
    assert captured_kwargs["timeout"] == getattr(settings, "OPENAI_TIMEOUT", 60.0)
    assert captured_kwargs["base_url"] is None
    assert captured_kwargs["max_retries"] == 0


def test_retry_after_ms_header_overrides_retry_after_and_backoff(monkeypatch):
    monkeypatch.setattr("openai_tts_gui.tts._service.random.uniform", lambda a, b: 0.0)

    assert (
        compute_backoff(
            FakeRateLimitError(headers={"retry-after-ms": "2500", "retry-after": "7"}),
            2,
        )
        == 2.5
    )
    assert compute_backoff(FakeRateLimitError(headers={"retry-after": "3"}), 2) == 3.0

    base = max(1.0, float(getattr(config, "RETRY_DELAY", 5)))
    assert compute_backoff(FakeRateLimitError(headers={}), 2) == base * 4


def test_429_reduces_run_cap_and_eventually_succeeds(monkeypatch, tmp_path):
    out = tmp_path / "rate-limit.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [
                FakeChunkOutcome(
                    error=FakeRateLimitError(
                        headers={"retry-after-ms": "1", "x-request-id": "rl-1"},
                        request_id="rl-1",
                    )
                ),
                FakeChunkOutcome(audio_bytes=b"one", request_id="req-1"),
            ],
            "chunk-2": [
                FakeChunkOutcome(audio_bytes=b"two", delay_seconds=0.05, request_id="req-2")
            ],
        }
    )
    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-1", "chunk-2"]
    )
    monkeypatch.setattr("openai_tts_gui.tts._service.RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(settings, "PARALLELISM", 2)

    service = TTSService(api_key="sk-test")
    waits: list[float] = []
    original_sleep = service._sleep_with_cancel

    def capture_sleep(wait_time, cancel_event):
        waits.append(wait_time)
        original_sleep(wait_time, cancel_event)

    monkeypatch.setattr(service, "_sleep_with_cancel", capture_sleep)
    service.generate(
        text="ignored because split_text is patched",
        output_path=str(out),
        model="tts-1",
        voice="alloy",
        response_format="wav",
        speed=1.0,
        instructions="",
        retain_files=False,
    )

    assert out.exists()
    assert len(concat_calls) == 1
    assert service._last_run_coordinator is not None
    assert service._last_run_coordinator.current_cap == 1
    assert waits == [0.001]


def test_api_status_500_retries_then_succeeds(monkeypatch, tmp_path):
    out = tmp_path / "server-retry.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-a": [
                FakeChunkOutcome(
                    error=FakeAPIStatusError("server error", status_code=500, request_id="srv-1")
                ),
                FakeChunkOutcome(audio_bytes=b"ok", request_id="srv-2"),
            ],
            "chunk-b": [
                FakeChunkOutcome(audio_bytes=b"peer", delay_seconds=0.05, request_id="peer-1")
            ],
        }
    )
    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-a", "chunk-b"]
    )
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)
    monkeypatch.setattr("openai_tts_gui.tts._service.compute_backoff", lambda exc, attempt: 0.01)
    monkeypatch.setattr(settings, "PARALLELISM", 2)

    service = TTSService(api_key="sk-test")
    waits: list[float] = []
    monkeypatch.setattr(
        service, "_sleep_with_cancel", lambda wait_time, cancel_event: waits.append(wait_time)
    )
    service.generate(
        text="ignored because split_text is patched",
        output_path=str(out),
        model="tts-1",
        voice="alloy",
        response_format="wav",
        speed=1.0,
        instructions="",
        retain_files=False,
    )

    assert out.exists()
    assert len(concat_calls) == 1
    assert [
        call["attempt"] for call in harness.api_calls if call["api_params"]["input"] == "chunk-a"
    ] == [1, 2]
    assert waits == [0.01]
    assert service._last_run_coordinator is not None
    assert service._last_run_coordinator.current_cap == 2


def test_non_retryable_401_fails_without_sleep(monkeypatch, tmp_path):
    out = tmp_path / "auth-fail.wav"
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

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-a"])
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)

    service = TTSService(api_key="sk-test")
    monkeypatch.setattr(
        service, "_sleep_with_cancel", lambda wait_time, cancel_event: sleeps.append(wait_time)
    )

    with pytest.raises(TTSAPIError) as exc_info:
        service.generate(
            text="ignored because split_text is patched",
            output_path=str(out),
            model="tts-1",
            voice="alloy",
            response_format="wav",
            speed=1.0,
            instructions="",
            retain_files=False,
        )

    assert "Status code: 401" in str(exc_info.value)
    assert sleeps == []
    assert concat_calls == []
    assert not out.exists()
