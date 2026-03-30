from __future__ import annotations

from pathlib import Path

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.errors import TTSAPIError, TTSCancelledError
from openai_tts_gui.tts import TTSService
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


def test_parallel_failure_skips_concat_and_cleans_temp_dir_when_retain_false(monkeypatch, tmp_path):
    out = tmp_path / "cleanup.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [
                FakeChunkOutcome(audio_bytes=b"one", delay_seconds=0.05, request_id="req-1")
            ],
            "chunk-2": [
                FakeChunkOutcome(
                    error=FakeAPIStatusError("auth error", status_code=401, request_id="auth-1")
                )
            ],
        }
    )

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-1", "chunk-2"]
    )
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)
    monkeypatch.setattr(settings, "PARALLELISM", 2)

    service = TTSService(api_key="sk-test")

    with pytest.raises(TTSAPIError):
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

    assert concat_calls == []
    assert not out.exists()
    assert not Path(str(out) + ".json").exists()
    assert not any(
        path.is_dir() and path.name.startswith("cleanup_chunks_") for path in tmp_path.iterdir()
    )


def test_parallel_failure_keeps_temp_dir_when_retain_true(monkeypatch, tmp_path):
    out = tmp_path / "retain.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [
                FakeChunkOutcome(audio_bytes=b"one", delay_seconds=0.05, request_id="req-1")
            ],
            "chunk-2": [
                FakeChunkOutcome(
                    error=FakeAPIStatusError("auth error", status_code=401, request_id="auth-1")
                )
            ],
        }
    )

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-1", "chunk-2"]
    )
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)
    monkeypatch.setattr(settings, "PARALLELISM", 2)

    service = TTSService(api_key="sk-test")

    with pytest.raises(TTSAPIError) as exc_info:
        service.generate(
            text="ignored because split_text is patched",
            output_path=str(out),
            model="tts-1",
            voice="alloy",
            response_format="wav",
            speed=1.0,
            instructions="",
            retain_files=True,
        )

    retained_dirs = [
        path
        for path in tmp_path.iterdir()
        if path.is_dir() and path.name.startswith("retain_chunks_")
    ]
    assert len(retained_dirs) == 1
    assert "Partial chunk files kept in" in str(exc_info.value)
    assert str(retained_dirs[0]) in str(exc_info.value)
    assert (retained_dirs[0] / "chunk_0001.wav").exists()
    assert concat_calls == []
    assert not out.exists()
    assert not Path(str(out) + ".json").exists()


def test_cancel_during_retry_aborts_without_final_output(monkeypatch, tmp_path):
    out = tmp_path / "cancel.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-a": [
                FakeChunkOutcome(
                    error=FakeRateLimitError(
                        headers={"retry-after-ms": "1", "x-request-id": "rate-1"},
                        request_id="rate-1",
                    )
                )
            ]
        }
    )
    import threading

    cancel_event = threading.Event()

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-a"])
    monkeypatch.setattr("openai_tts_gui.tts._service.RateLimitError", FakeRateLimitError)

    service = TTSService(api_key="sk-test")

    def fake_sleep(wait_time, active_cancel_event):
        cancel_event.set()
        raise TTSCancelledError("TTS generation cancelled.")

    monkeypatch.setattr(service, "_sleep_with_cancel", fake_sleep)

    with pytest.raises(TTSCancelledError):
        service.generate(
            text="ignored because split_text is patched",
            output_path=str(out),
            model="tts-1",
            voice="alloy",
            response_format="wav",
            speed=1.0,
            instructions="",
            retain_files=False,
            cancel_event=cancel_event,
        )

    assert concat_calls == []
    assert not out.exists()
    assert not Path(str(out) + ".json").exists()
