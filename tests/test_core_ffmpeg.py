from __future__ import annotations

from types import SimpleNamespace

from openai_tts_gui.core import ffmpeg


def test_ffmpeg_probe_is_cached_between_preflight_and_about(monkeypatch):
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        return SimpleNamespace(stdout="ffmpeg version 7.1\n", stderr="")

    ffmpeg._run_ffmpeg_version.cache_clear()
    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)

    ok, detail = ffmpeg.preflight_check()
    version = ffmpeg.get_ffmpeg_version()

    assert ok is True
    assert detail == "ffmpeg version 7.1"
    assert version == "ffmpeg version 7.1"
    assert calls["count"] == 1

    ffmpeg._run_ffmpeg_version.cache_clear()
