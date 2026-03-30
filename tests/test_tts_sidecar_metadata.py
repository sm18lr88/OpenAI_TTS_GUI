from __future__ import annotations

import json
from pathlib import Path

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.errors import TTSAPIError
from openai_tts_gui.tts import TTSService
from tests.fakes_tts_service import FakeAPIStatusError, FakeChunkOutcome, FakeTTSServiceHarness


def _patch_basic_generate(monkeypatch, harness, concat_calls):
    def fake_concat(files: list[str], output_path: str) -> None:
        concat_calls.append(list(files))
        Path(output_path).write_bytes(b"joined-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fake_concat)


def test_sidecar_request_meta_sorted_by_chunk_index(monkeypatch, tmp_path):
    out = tmp_path / "ordered-sidecar.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [
                FakeChunkOutcome(audio_bytes=b"one", delay_seconds=0.2, request_id="req-1")
            ],
            "chunk-2": [
                FakeChunkOutcome(audio_bytes=b"two", delay_seconds=0.05, request_id="req-2")
            ],
            "chunk-3": [FakeChunkOutcome(audio_bytes=b"three", request_id="req-3")],
        }
    )

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text",
        lambda text, size: ["chunk-1", "chunk-2", "chunk-3"],
    )
    monkeypatch.setattr(settings, "PARALLELISM", 3)

    service = TTSService(api_key="sk-test")
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

    meta = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))
    assert [item["chunk_index"] for item in meta["request_meta"]] == [1, 2, 3]
    assert len(concat_calls) == 1


def test_sidecar_parallelism_used_is_effective_worker_count(monkeypatch, tmp_path):
    out = tmp_path / "parallelism.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-1")],
            "chunk-2": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-2")],
        }
    )

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-1", "chunk-2"]
    )
    monkeypatch.setattr(settings, "PARALLELISM", 4)

    service = TTSService(api_key="sk-test")
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

    meta = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))
    assert meta["parallelism_used"] == 2
    assert len(concat_calls) == 1


def test_requested_parallelism_overrides_default_setting(monkeypatch, tmp_path):
    out = tmp_path / "requested-parallelism.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [FakeChunkOutcome(audio_bytes=b"one", request_id="req-1")],
            "chunk-2": [FakeChunkOutcome(audio_bytes=b"two", request_id="req-2")],
        }
    )

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-1", "chunk-2"]
    )
    monkeypatch.setattr(settings, "PARALLELISM", 1)

    service = TTSService(api_key="sk-test")
    service.generate(
        text="ignored because split_text is patched",
        output_path=str(out),
        model="tts-1",
        voice="alloy",
        response_format="wav",
        speed=1.0,
        instructions="",
        parallelism=2,
        retain_files=False,
    )

    meta = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))
    assert meta["parallelism_requested"] == 2
    assert meta["parallelism_used"] == 2
    assert len(concat_calls) == 1


def test_request_meta_records_attempt_count_and_request_id(monkeypatch, tmp_path):
    out = tmp_path / "request-meta.wav"
    concat_calls: list[list[str]] = []
    harness = FakeTTSServiceHarness(
        {
            "chunk-a": [
                FakeChunkOutcome(
                    error=FakeAPIStatusError("server error", status_code=500, request_id="srv-1")
                ),
                FakeChunkOutcome(
                    audio_bytes=b"ok",
                    request_id="srv-2",
                    headers={"retry-after-ms": "10", "retry-after": "1", "x-request-id": "srv-2"},
                ),
            ]
        }
    )

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-a"])
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)
    monkeypatch.setattr("openai_tts_gui.tts._service.compute_backoff", lambda exc, attempt: 0.0)

    service = TTSService(api_key="sk-test")
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

    request_meta = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))["request_meta"][
        0
    ]
    assert request_meta["attempts"] == 2
    assert request_meta["characters"] == len("chunk-a")
    assert request_meta["request_id"] == "srv-2"
    assert request_meta["retry_headers"] == {"retry-after-ms": "10", "retry-after": "1"}
    assert len(concat_calls) == 1


def test_failed_run_does_not_write_success_sidecar(monkeypatch, tmp_path):
    out = tmp_path / "failed-sidecar.wav"
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

    _patch_basic_generate(monkeypatch, harness, concat_calls)
    monkeypatch.setattr("openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-a"])
    monkeypatch.setattr("openai_tts_gui.tts._service.APIStatusError", FakeAPIStatusError)

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
    assert not Path(str(out) + ".json").exists()
