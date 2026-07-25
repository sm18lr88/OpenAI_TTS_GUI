from __future__ import annotations

from pathlib import Path


def patch_rate_limit_generation_seams(monkeypatch, harness, concat_calls):
    def fake_concat(files: list[str], output_path: str) -> None:
        concat_calls.append(list(files))
        Path(output_path).write_bytes(b"joined-audio")

    monkeypatch.setattr("openai_tts_gui.tts._service.OpenAI", harness.openai_class())
    monkeypatch.setattr("openai_tts_gui.tts._service.require_preflight", lambda: "ffmpeg OK")
    monkeypatch.setattr("openai_tts_gui.tts._service.concatenate_audio_files", fake_concat)
