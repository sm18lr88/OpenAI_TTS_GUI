import json
from pathlib import Path

import pytest

from openai_tts_gui.config import app_settings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, 1),
        (False, 1),
        ("bad", 1),
        ("2", 2),
        (0, 1),
        (9, 8),
        (2.5, 1),
        (None, 1),
    ],
)
def test_clamp_parallelism_normalizes_supported_values(
    value: bool | str | int | float | None,
    expected: int,
) -> None:
    assert app_settings._clamp_parallelism(value) == expected


@pytest.mark.parametrize("content", ["{", "[]", "null", '"text"'])
def test_load_app_settings_returns_defaults_for_missing_or_invalid_data(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "settings.json"
    defaults = app_settings.default_app_settings()
    assert app_settings.load_app_settings(str(path)) == defaults
    path.write_text(content, encoding="utf-8")
    assert app_settings.load_app_settings(str(path)) == defaults


def test_load_app_settings_normalizes_mixed_payload_and_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"parallelism": "99", "parallelism_warning_shown": "false", "retain_files": 0}),
        encoding="utf-8",
    )
    assert app_settings.load_app_settings(str(path)) == {
        "parallelism": 8,
        "parallelism_warning_shown": True,
        "retain_files": False,
    }

    def fail_open(self: Path, *, encoding: str):
        raise PermissionError("read failure")

    monkeypatch.setattr(Path, "open", fail_open)
    assert app_settings.load_app_settings(str(path)) == app_settings.default_app_settings()


def test_save_app_settings_round_trips_normalized_unicode_payload(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "settings.json"
    app_settings_payload = {
        "parallelism": "3",
        "parallelism_warning_shown": "yes",
        "retain_files": 1,
        "ignored": "λ",
    }
    assert app_settings.save_app_settings(app_settings_payload, str(path))
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "parallelism": 3,
        "parallelism_warning_shown": True,
        "retain_files": True,
    }


@pytest.mark.parametrize("failure", ["mkdir", "replace"])
def test_save_app_settings_handles_atomic_write_errors_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    path = tmp_path / "nested" / "settings.json"
    path.parent.mkdir()
    path.write_text('{"parallelism": 2}\n', encoding="utf-8")

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
        monkeypatch.setattr(app_settings.os, "replace", fail_replace)
    assert not app_settings.save_app_settings({}, str(path))
    assert path.read_text(encoding="utf-8") == '{"parallelism": 2}\n'
    assert list(path.parent.glob("*.tmp")) == []


def test_save_app_settings_surfaces_unlink_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace")

    def fail_unlink(self: Path, *, missing_ok: bool = False) -> None:
        raise PermissionError("unlink")

    monkeypatch.setattr(app_settings.os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(PermissionError, match="unlink"):
        app_settings.save_app_settings({}, str(path))
