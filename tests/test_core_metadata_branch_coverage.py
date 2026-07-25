from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import NoReturn

import pytest

from openai_tts_gui.core import metadata


class MetadataSerializationError(Exception):
    pass


def test_sidecar_creates_nested_parent_with_generated_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "nested" / "audio.wav"
    monkeypatch.setattr(metadata, "get_ffmpeg_version", lambda: "ffmpeg version test")
    monkeypatch.setattr(metadata.platform, "platform", lambda: "test-os")

    sidecar = Path(metadata.write_sidecar_metadata(str(output), {}))
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert sidecar == Path(f"{output}.json")
    assert payload["ffmpeg"] == "ffmpeg version test"
    assert payload["os"] == "test-os"
    assert "timestamp" in payload
    assert not list(sidecar.parent.glob("audio.wav.*.tmp"))


def test_sidecar_preserves_explicit_defaults_and_stringifies_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "audio.wav"
    monkeypatch.setattr(metadata, "get_ffmpeg_version", lambda: "generated")
    monkeypatch.setattr(metadata.platform, "platform", lambda: "generated-os")
    supplied_path = tmp_path / "source.wav"

    sidecar = Path(
        metadata.write_sidecar_metadata(
            str(output),
            {
                "timestamp": "provided-time",
                "ffmpeg": "provided-ffmpeg",
                "os": "provided-os",
                "source": supplied_path,
            },
        )
    )
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert payload == {
        "ffmpeg": "provided-ffmpeg",
        "os": "provided-os",
        "source": str(supplied_path),
        "timestamp": "provided-time",
    }


def test_sidecar_atomically_replaces_existing_content(tmp_path: Path) -> None:
    output = tmp_path / "audio.wav"
    sidecar = Path(f"{output}.json")
    sidecar.write_text('{"stale": true}\n', encoding="utf-8")

    metadata.write_sidecar_metadata(
        str(output),
        {"timestamp": "new", "ffmpeg": "test", "os": "test", "model": "tts"},
    )

    assert json.loads(sidecar.read_text(encoding="utf-8")) == {
        "ffmpeg": "test",
        "model": "tts",
        "os": "test",
        "timestamp": "new",
    }
    assert not list(tmp_path.glob("audio.wav.*.tmp"))


def test_sidecar_removes_temp_file_when_atomic_replace_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "audio.wav"
    sidecar = Path(f"{output}.json")
    sidecar.write_text('{"old": true}\n', encoding="utf-8")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("replace blocked")

    monkeypatch.setattr(metadata.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace blocked"):
        metadata.write_sidecar_metadata(str(output), {})

    assert json.loads(sidecar.read_text(encoding="utf-8")) == {"old": True}
    assert not list(tmp_path.glob("audio.wav.*.tmp"))


def test_sidecar_removes_temp_file_when_value_serialization_fails(tmp_path: Path) -> None:
    output = tmp_path / "audio.wav"

    def fail_dump(*_args: str, **_kwargs: str) -> NoReturn:
        raise MetadataSerializationError("cannot stringify")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(metadata.json, "dump", fail_dump)
    with pytest.raises(MetadataSerializationError, match="cannot stringify"):
        metadata.write_sidecar_metadata(str(output), {"bad": "value"})
    monkeypatch.undo()

    assert not list(tmp_path.glob("audio.wav.*.tmp"))


def test_sha256_text_hashes_unicode_and_empty_input() -> None:
    text = "Speech \u2014 \u97f3\u58f0"

    assert metadata.sha256_text(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert metadata.sha256_text("") == hashlib.sha256(b"").hexdigest()
