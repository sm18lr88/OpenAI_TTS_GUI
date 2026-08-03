from __future__ import annotations

import subprocess
import wave
from collections.abc import Callable
from pathlib import Path
from typing import assert_never

import pytest

from openai_tts_gui.core import audio
from openai_tts_gui.core._ffmpeg_process import ProcessOutput
from openai_tts_gui.core.ffmpeg import require_preflight
from openai_tts_gui.errors import FFmpegError, FFmpegNotFoundError, TTSChunkError


def _write_wav(path: Path, frames: int = 4_800) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00\x00\x00" * frames)


def test_concatenate_rejects_empty_and_missing_inputs(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "out.wav"

    with pytest.raises(TTSChunkError, match="No audio files"):
        audio.concatenate_audio_files([], str(output))
    with pytest.raises(TTSChunkError, match="missing.wav"):
        audio.concatenate_audio_files([str(tmp_path / "missing.wav")], str(output))


def test_single_input_same_destination_preserves_file(tmp_path: Path) -> None:
    source = tmp_path / "same.wav"
    _write_wav(source)

    result = audio.concatenate_audio_files([str(source)], str(source))

    assert result == str(source)
    assert source.exists()


def test_single_input_replaces_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "nested" / "destination.wav"
    _write_wav(source)
    destination.parent.mkdir()
    destination.write_bytes(b"old")

    result = audio.concatenate_audio_files([str(source)], str(destination))

    assert result == str(destination)
    assert not source.exists()
    with wave.open(str(destination), "rb") as handle:
        assert handle.getnframes() == 4_800


def test_single_input_moves_to_new_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "nested" / "destination.wav"
    _write_wav(source)

    audio.concatenate_audio_files([str(source)], str(destination))

    assert destination.exists()
    assert not source.exists()


def test_single_input_translates_move_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "destination.wav"
    _write_wav(source)

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replace blocked")

    monkeypatch.setattr(audio.os, "replace", fail_replace)

    with pytest.raises(TTSChunkError, match="replace blocked") as error:
        audio.concatenate_audio_files([str(source)], str(destination))

    assert error.value.file_path == str(destination)


def test_real_ffmpeg_concatenates_nested_wavs_and_ffprobe_reads_output(tmp_path: Path) -> None:
    require_preflight()
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "nested" / "joined.wav"
    _write_wav(first)
    _write_wav(second, frames=9_600)

    audio.concatenate_audio_files([str(first), str(second)], str(output))
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert output.exists()
    assert 0.29 <= float(probe.stdout.strip()) <= 0.31
    assert not list(output.parent.glob("concat_*.txt"))


def test_concat_command_adds_codec_parameters_and_removes_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write_wav(first)
    _write_wav(second)
    commands: list[list[str]] = []

    class FakeProcess:
        def __init__(self, command: list[str]) -> None:
            commands.append(command)

        def run(self, _on_started: Callable[[FakeProcess], bool] | None = None) -> ProcessOutput:
            return ProcessOutput("", "", 0, False, False)

    monkeypatch.setattr(audio, "resolve_ffmpeg_command", lambda: "ffmpeg")
    monkeypatch.setattr(audio, "FfmpegProcess", FakeProcess)

    audio.concatenate_audio_files([str(first), str(second)], str(tmp_path / "joined.mp3"))

    assert commands[0][commands[0].index("-c:a") + 1] == "libmp3lame"
    assert commands[0][-7:-1] == ["-ar", "48000", "-ac", "2", "-b:a", "192k"]
    assert not list(tmp_path.glob("concat_*.txt"))


def test_concat_uses_default_codec_without_optional_parameters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write_wav(first)
    _write_wav(second)
    command: list[str] = []

    class FakeProcess:
        def __init__(self, args: list[str]) -> None:
            command.extend(args)

        def run(self, _on_started: Callable[[FakeProcess], bool] | None = None) -> ProcessOutput:
            return ProcessOutput("", "", 0, False, False)

    monkeypatch.setattr(audio, "resolve_ffmpeg_command", lambda: "ffmpeg")
    monkeypatch.setattr(audio, "FfmpegProcess", FakeProcess)

    audio.concatenate_audio_files([str(first), str(second)], str(tmp_path / "joined.custom"))

    assert command[command.index("-c:a") + 1] == "copy"
    assert "-ar" not in command and "-ac" not in command and "-b:a" not in command


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (FFmpegNotFoundError("missing"), FFmpegNotFoundError),
        (ProcessOutput("", "bad input", 7, False, False), FFmpegError),
        (ProcessOutput("", "", 7, False, False), FFmpegError),
        (OSError("disk error"), TTSChunkError),
    ],
)
def test_concat_translates_adapter_errors_and_cleans_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    result: OSError | FFmpegNotFoundError | ProcessOutput,
    expected: type[Exception],
) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write_wav(first)
    _write_wav(second)

    class FakeProcess:
        def __init__(self, _command: list[str]) -> None:
            return None

        def run(self, _on_started: Callable[[FakeProcess], bool] | None = None) -> ProcessOutput:
            match result:
                case ProcessOutput():
                    return result
                case (OSError() | FFmpegNotFoundError()) as error:
                    raise error
                case unreachable:
                    assert_never(unreachable)

    monkeypatch.setattr(audio, "resolve_ffmpeg_command", lambda: "ffmpeg")
    monkeypatch.setattr(audio, "FfmpegProcess", FakeProcess)

    with pytest.raises(expected):
        audio.concatenate_audio_files([str(first), str(second)], str(tmp_path / "joined.wav"))

    assert not list(tmp_path.glob("concat_*.txt"))


def test_concat_logs_but_preserves_success_when_list_cleanup_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write_wav(first)
    _write_wav(second)
    original_unlink = Path.unlink

    def selective_unlink(path: Path, **kwargs: bool) -> None:
        if path.name.startswith("concat_"):
            raise OSError("locked")
        original_unlink(path, **kwargs)

    monkeypatch.setattr(audio, "resolve_ffmpeg_command", lambda: "ffmpeg")

    class FakeProcess:
        def __init__(self, _command: list[str]) -> None:
            return None

        def run(self, _on_started: Callable[[FakeProcess], bool] | None = None) -> ProcessOutput:
            return ProcessOutput("", "", 0, False, False)

    monkeypatch.setattr(audio, "FfmpegProcess", FakeProcess)
    monkeypatch.setattr(Path, "unlink", selective_unlink)

    result = audio.concatenate_audio_files([str(first), str(second)], str(tmp_path / "joined.wav"))
    leftovers = list(tmp_path.glob("concat_*.txt"))

    assert result == str(tmp_path / "joined.wav")
    assert "Could not remove the temporary concat list" in caplog.text
    original_unlink(leftovers[0])


def test_cleanup_files_ignores_missing_and_suppresses_unlink_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    present = tmp_path / "present.wav"
    blocked = tmp_path / "blocked.wav"
    _write_wav(present)
    _write_wav(blocked)
    original_unlink = Path.unlink

    def selective_unlink(path: Path, **kwargs: bool) -> None:
        if path == blocked:
            raise OSError("locked")
        original_unlink(path, **kwargs)

    monkeypatch.setattr(Path, "unlink", selective_unlink)

    audio.cleanup_files([str(present), str(tmp_path / "missing.wav"), str(blocked)])

    assert not present.exists()
    assert blocked.exists()
