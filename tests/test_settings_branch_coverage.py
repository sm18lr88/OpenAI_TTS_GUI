import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from openai_tts_gui import config
from openai_tts_gui.config import settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 3), ("bad", 3), ("0", 1), ("9", 8), ("4", 4)],
)
def test_read_int_env_uses_default_and_clamps(
    monkeypatch: pytest.MonkeyPatch,
    raw: str | None,
    expected: int,
) -> None:
    if raw is None:
        monkeypatch.delenv("TTS_TEST_PARALLELISM", raising=False)
    else:
        monkeypatch.setenv("TTS_TEST_PARALLELISM", raw)
    assert settings._read_int_env("TTS_TEST_PARALLELISM", 3, minimum=1, maximum=8) == expected


@pytest.mark.parametrize(
    ("parallelism", "stream", "base_url", "expected"),
    [
        ("0", "invalid", "", [1, "audio", None]),
        ("8", "sse", "https://local.example", [8, "sse", "https://local.example"]),
    ],
)
def test_settings_environment_import_isolated_in_subprocess(
    parallelism: str,
    stream: str,
    base_url: str,
    expected: list[int | str | None],
) -> None:
    source = Path(__file__).parents[1] / "src"
    code = (
        "import json; from openai_tts_gui.config import settings; "
        "print(json.dumps([settings.PARALLELISM, settings.STREAM_FORMAT, "
        "settings.OPENAI_BASE_URL]))"
    )
    environment = {
        "PYTHONPATH": str(source),
        "TTS_PARALLELISM": parallelism,
        "TTS_STREAM_FORMAT": stream,
        "OPENAI_BASE_URL": base_url,
    }
    for name in ("PATH", "SYSTEMROOT", "WINDIR"):
        if value := os.environ.get(name):
            environment[name] = value
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )
    assert json.loads(result.stdout) == expected


def test_version_and_dependency_snapshot_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise settings.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(settings.metadata, "version", missing)
    assert settings._resolve_app_version() == settings.DEFAULT_APP_VERSION
    snapshot = settings.env_snapshot()
    assert snapshot["openai"] == "unknown"
    assert snapshot["pyqt6"] == "unknown"
    assert {"app_name", "app_version", "python", "platform"} <= snapshot.keys()


def test_version_fallback_and_invalid_stream_format(monkeypatch: pytest.MonkeyPatch) -> None:
    class _InjectedMetadataLookupError(Exception):
        pass

    def fail_version(name: str) -> str:
        raise _InjectedMetadataLookupError("metadata failure")

    with monkeypatch.context() as metadata_patch:
        metadata_patch.setattr(settings.metadata, "version", fail_version)
        with pytest.raises(_InjectedMetadataLookupError, match="metadata failure"):
            settings._resolve_app_version()
    monkeypatch.setenv("TTS_STREAM_FORMAT", "invalid")
    importlib.reload(settings)
    assert settings.STREAM_FORMAT == "audio"


def test_directory_and_config_facade_exports(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        settings.os,
        "makedirs",
        lambda path, exist_ok: calls.append((path, exist_ok)),
    )
    settings.ensure_directories()
    assert calls == [(settings.DATA_DIR, True), (settings.DEFAULT_OUTPUT_DIR, True)]
    assert config.load_app_settings.__module__ == "openai_tts_gui.config.app_settings"
    assert config.save_app_settings.__module__ == "openai_tts_gui.config.app_settings"
    with pytest.raises(AttributeError):
        config.__getattr__("not_a_config_export")
