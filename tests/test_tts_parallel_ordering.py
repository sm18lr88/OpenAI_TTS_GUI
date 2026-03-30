from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openai_tts_gui.config import settings
from openai_tts_gui.errors import TTSChunkError
from openai_tts_gui.tts import TTSService
from tests.fakes_tts_service import FakeChunkOutcome, FakeTTSServiceHarness


def test_fake_provider_smoke(monkeypatch, tmp_path):
    out = tmp_path / "out.wav"
    harness = FakeTTSServiceHarness(
        {
            "Hello world.": [
                FakeChunkOutcome(
                    audio_bytes=b"fake-audio",
                    request_id="req-123",
                    headers={"openai-model": "tts-1", "x-request-id": "req-123"},
                )
            ]
        }
    )
    concat_calls: list[list[str]] = []

    def fake_concat(files: list[str], output_path: str) -> None:
        concat_calls.append(list(files))
        Path(output_path).write_bytes(b"joined-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fake_concat)

    service = TTSService(api_key="sk-test")
    message = service.generate(
        text="Hello world.",
        output_path=str(out),
        model="tts-1",
        voice="alloy",
        response_format="wav",
        speed=1.0,
        instructions="",
        retain_files=False,
    )

    assert out.exists()
    assert "saved successfully" in message
    assert len(concat_calls) == 1
    assert len(concat_calls[0]) == 1
    assert Path(concat_calls[0][0]).name == "chunk_0001.wav"
    assert harness.client_kwargs == [
        {
            "api_key": "sk-test",
            "timeout": getattr(settings, "OPENAI_TIMEOUT", 60.0),
            "base_url": None,
            "max_retries": 0,
        }
    ]
    assert harness.api_calls == [
        {
            "attempt": 1,
            "api_params": {
                "model": "tts-1",
                "voice": "alloy",
                "input": "Hello world.",
                "response_format": "wav",
                "speed": 1.0,
                "stream_format": getattr(settings, "STREAM_FORMAT", "audio"),
            },
            "thread_name": harness.api_calls[0]["thread_name"],
        }
    ]
    assert harness.write_order == [concat_calls[0][0]]
    assert not Path(concat_calls[0][0]).exists()

    sidecar_path = Path(str(out) + ".json")
    meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert meta["stream_format"] == getattr(settings, "STREAM_FORMAT", None)
    assert meta["chunk_count"] == 1
    assert meta["request_meta"] == [
        {
            "chunk_index": 1,
            "request_id": "req-123",
            "model_header": "tts-1",
            "file": concat_calls[0][0],
            "attempts": 1,
            "characters": len("Hello world."),
            "retry_headers": None,
        }
    ]


def test_parallel_out_of_order_completion_concatenates_by_chunk_index(monkeypatch, tmp_path):
    out = tmp_path / "parallel.wav"
    harness = FakeTTSServiceHarness(
        {
            "chunk-1": [
                FakeChunkOutcome(
                    audio_bytes=b"one",
                    delay_seconds=0.2,
                    request_id="req-1",
                    headers={"openai-model": "tts-1", "x-request-id": "req-1"},
                )
            ],
            "chunk-2": [
                FakeChunkOutcome(
                    audio_bytes=b"two",
                    delay_seconds=0.05,
                    request_id="req-2",
                    headers={"openai-model": "tts-1", "x-request-id": "req-2"},
                )
            ],
            "chunk-3": [
                FakeChunkOutcome(
                    audio_bytes=b"three",
                    request_id="req-3",
                    headers={"openai-model": "tts-1", "x-request-id": "req-3"},
                )
            ],
        }
    )
    concat_calls: list[list[str]] = []

    def fake_concat(files: list[str], output_path: str) -> None:
        concat_calls.append(list(files))
        Path(output_path).write_bytes(b"joined-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fake_concat)
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

    assert len(concat_calls) == 1
    assert [Path(path).name for path in concat_calls[0]] == [
        "chunk_0001.wav",
        "chunk_0002.wav",
        "chunk_0003.wav",
    ]
    assert [Path(path).name for path in harness.write_order][-1] == "chunk_0001.wav"

    sidecar_path = Path(str(out) + ".json")
    meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert [item["chunk_index"] for item in meta["request_meta"]] == [1, 2, 3]


def test_parallel_duplicate_chunk_result_rejected_before_concat(monkeypatch, tmp_path):
    out = tmp_path / "duplicate.wav"
    concat_calls: list[list[str]] = []

    def fake_concat(files: list[str], output_path: str) -> None:
        concat_calls.append(list(files))
        Path(output_path).write_bytes(b"joined-audio")

    def fake_generate_chunk(self, *, task, **kwargs):
        return SimpleNamespace(
            chunk_index=1,
            request_id=f"dup-{task.index}",
            model_header="tts-1",
            file=str(task.filename),
            attempts=1,
            characters=len(task.text),
            retry_headers=None,
        )

    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fake_concat)
    monkeypatch.setattr(
        "openai_tts_gui.tts._service.split_text", lambda text, size: ["chunk-1", "chunk-2"]
    )
    monkeypatch.setattr(TTSService, "_generate_chunk_with_retries", fake_generate_chunk)
    monkeypatch.setattr(settings, "PARALLELISM", 2)

    service = TTSService(api_key="sk-test")

    with pytest.raises(TTSChunkError) as exc_info:
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

    assert "Duplicate chunk result" in str(exc_info.value)
    assert concat_calls == []
    assert not out.exists()
    assert not Path(str(out) + ".json").exists()
