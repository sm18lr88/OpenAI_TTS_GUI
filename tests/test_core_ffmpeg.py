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


def test_resolve_ffmpeg_command_uses_registry_path(monkeypatch, tmp_path):
    ffmpeg_bin = tmp_path / "ffmpeg.exe"
    ffmpeg_bin.write_text("", encoding="utf-8")

    ffmpeg.resolve_ffmpeg_command.cache_clear()
    monkeypatch.setattr(
        ffmpeg.os.environ,
        "get",
        lambda name, default="": "" if name == "PATH" else default,
    )
    monkeypatch.setattr(ffmpeg, "_windows_registry_path", lambda: str(tmp_path))
    monkeypatch.setattr(ffmpeg, "_packaged_search_dirs", lambda: [])
    monkeypatch.setattr(ffmpeg, "_common_windows_ffmpeg_dirs", lambda: [])

    assert ffmpeg.resolve_ffmpeg_command().lower() == str(ffmpeg_bin).lower()
    ffmpeg.resolve_ffmpeg_command.cache_clear()


def test_resolve_ffmpeg_command_checks_common_windows_dirs(monkeypatch, tmp_path):
    ffmpeg_bin = tmp_path / "ffmpeg.exe"
    ffmpeg_bin.write_text("", encoding="utf-8")

    ffmpeg.resolve_ffmpeg_command.cache_clear()
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ffmpeg, "_windows_registry_path", lambda: "")
    monkeypatch.setattr(ffmpeg, "_packaged_search_dirs", lambda: [])
    monkeypatch.setattr(ffmpeg, "_common_windows_ffmpeg_dirs", lambda: [tmp_path])

    assert ffmpeg.resolve_ffmpeg_command() == str(ffmpeg_bin)
    ffmpeg.resolve_ffmpeg_command.cache_clear()
