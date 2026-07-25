from __future__ import annotations

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.errors import TTSAPIError
from openai_tts_gui.tts import TTSService
from tests.fakes_tts_service import (
    FakeAPIStatusError,
    FakeChunkOutcome,
    FakeRateLimitError,
    FakeTTSServiceHarness,
)
from tests.tts_rate_limit_support import patch_rate_limit_generation_seams


def test_429_reduces_run_cap_and_eventually_succeeds(monkeypatch, tmp_path):
    # Given: two chunks where the first receives a rate limit then succeeds.
    output = tmp_path / "rate-limit.wav"
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
    patch_rate_limit_generation_seams(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda *_args: ["chunk-1", "chunk-2"]
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

    # When: generation retries the rate-limited chunk alongside its peer.
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

    # Then: the audio completes after one concatenation and the run cap is reduced.
    assert output.exists()
    assert len(concat_calls) == 1
    assert service._last_run_coordinator is not None
    assert service._last_run_coordinator.current_cap == 1
    assert waits == [0.001]


def test_api_status_500_remains_single_attempt_and_does_not_reduce_capacity(monkeypatch, tmp_path):
    # Given: two chunks where one receives an uncertain server failure.
    output = tmp_path / "server-retry.wav"
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
    patch_rate_limit_generation_seams(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda *_args: ["chunk-a", "chunk-b"]
    )
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)
    monkeypatch.setattr(settings, "PARALLELISM", 2)
    service = TTSService(api_key="sk-test")
    waits: list[float] = []
    monkeypatch.setattr(
        service, "_sleep_with_cancel", lambda wait_time, _cancel_event: waits.append(wait_time)
    )

    # When: generation receives the server-failed chunk.
    with pytest.raises(TTSAPIError):
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

    # Then: the uncertain fault is not retried or admitted to final publication.
    assert not output.exists()
    assert concat_calls == []
    assert [
        call["attempt"] for call in harness.api_calls if call["api_params"]["input"] == "chunk-a"
    ] == [1]
    assert waits == []
    assert service._last_run_coordinator is not None
    assert service._last_run_coordinator.current_cap == 2
