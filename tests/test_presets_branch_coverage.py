import json
from pathlib import Path
from typing import NoReturn, Protocol

import pytest

from openai_tts_gui.presets import _storage


class _JsonTextReader(Protocol):
    def read(self, size: int = -1) -> str: ...


class _JsonTextWriter(Protocol):
    def write(self, data: str) -> int: ...


class _InjectedJsonLoadError(Exception):
    pass


@pytest.mark.parametrize("content", ["{", "[]", "null", '"text"'])
def test_load_presets_returns_empty_for_missing_or_invalid_data(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "presets.json"
    assert _storage.load_presets(str(path)) == {}
    path.write_text(content, encoding="utf-8")
    assert _storage.load_presets(str(path)) == {}


def test_load_presets_filters_mixed_entries_and_preserves_unicode(tmp_path: Path) -> None:
    path = tmp_path / "presets.json"
    path.write_text(
        json.dumps({"warm": "Hello", "cafe-東京": "λ", "bad": 1, "also_bad": None}),
        encoding="utf-8",
    )
    assert _storage.load_presets(str(path)) == {"warm": "Hello", "cafe-東京": "λ"}


def test_load_presets_handles_os_errors_and_surfaces_unexpected_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "presets.json"
    path.write_text("{}", encoding="utf-8")

    def fail_open(self: Path, *, encoding: str):
        raise PermissionError("read failure")

    monkeypatch.setattr(Path, "open", fail_open)
    assert _storage.load_presets(str(path)) == {}

    monkeypatch.undo()

    def fail_load(file: _JsonTextReader) -> NoReturn:
        raise _InjectedJsonLoadError("bad")

    monkeypatch.setattr(_storage.json, "load", fail_load)
    with pytest.raises(_InjectedJsonLoadError, match="bad"):
        _storage.load_presets(str(path))


def test_save_presets_round_trips_unicode_atomically(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "presets.json"
    presets = {"cafe-東京": "λ prompt", "warm": "hello"}
    assert _storage.save_presets(presets, str(path))
    assert _storage.load_presets(str(path)) == presets
    assert "λ prompt" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("failure", ["mkdir", "replace"])
def test_save_presets_handles_write_errors_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    path = tmp_path / "nested" / "presets.json"
    path.parent.mkdir()
    path.write_text('{"old": "value"}\n', encoding="utf-8")

    def fail_mkdir(
        self: Path,
        *,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        raise OSError("mkdir")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace")

    if failure == "mkdir":
        monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    else:
        monkeypatch.setattr(_storage.os, "replace", fail_replace)
    assert not _storage.save_presets({"new": "value"}, str(path))
    assert path.read_text(encoding="utf-8") == '{"old": "value"}\n'
    assert list(path.parent.glob("*.tmp")) == []


def test_save_presets_surfaces_serialization_and_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "presets.json"

    def fail_dump(
        presets: dict[str, str],
        file: _JsonTextWriter,
        **kwargs: str | int | bool,
    ) -> NoReturn:
        raise TypeError("not serializable")

    monkeypatch.setattr(_storage.json, "dump", fail_dump)
    with pytest.raises(TypeError):
        _storage.save_presets({"bad": "value"}, str(path))

    monkeypatch.undo()

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace")

    def fail_unlink(self: Path, *, missing_ok: bool = False) -> None:
        raise PermissionError("unlink")

    monkeypatch.setattr(_storage.os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(PermissionError, match="unlink"):
        _storage.save_presets({"good": "value"}, str(path))
