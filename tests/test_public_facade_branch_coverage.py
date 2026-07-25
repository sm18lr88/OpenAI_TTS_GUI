from __future__ import annotations

from importlib import metadata

import pytest

import openai_tts_gui as package
from openai_tts_gui import config, core, gui, tts
from openai_tts_gui.gui.workers import TTSWorker


def test_package_version_uses_fallback_for_missing_metadata(monkeypatch):
    def failing_version(_distribution):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(package.metadata, "version", failing_version)

    when_version = package._resolve_package_version()

    assert when_version == package.DEFAULT_APP_VERSION


def test_package_version_surfaces_unexpected_metadata_errors(monkeypatch):
    class _InjectedMetadataLookupError(Exception):
        pass

    def failing_version(_distribution):
        raise _InjectedMetadataLookupError("metadata failure")

    monkeypatch.setattr(package.metadata, "version", failing_version)

    with pytest.raises(_InjectedMetadataLookupError, match="metadata failure"):
        package._resolve_package_version()


@pytest.mark.parametrize("name", ["TTSService", "preflight_check", "split_text"])
def test_package_lazy_exports_are_resolved(name):
    when_export = getattr(package, name)

    assert callable(when_export)


@pytest.mark.parametrize(
    ("facade", "name"),
    [
        (package, "missing_export"),
        (config, "missing_export"),
        (core, "missing_export"),
        (gui, "missing_export"),
        (tts, "missing_export"),
    ],
)
def test_public_facades_reject_invalid_exports(facade, name):
    with pytest.raises(AttributeError):
        getattr(facade, name)


@pytest.mark.parametrize(
    "name", ["DARK_THEME", "LIGHT_THEME", "apply_fusion_dark", "build_stylesheet"]
)
def test_config_lazy_theme_exports_are_resolved(name):
    when_export = getattr(config, name)

    assert when_export is not None


@pytest.mark.parametrize(
    "name",
    [
        "cleanup_files",
        "get_ffmpeg_version",
        "sha256_text",
        "split_text",
    ],
)
def test_core_lazy_export_groups_are_resolved(name):
    when_export = getattr(core, name)

    assert callable(when_export)


@pytest.mark.parametrize(
    "name",
    ["ApiKeyLoadWorker", "PresetDialog", "FFmpegPreflightWorker", "TTSWindow", "TTSWorker"],
)
def test_gui_lazy_exports_are_resolved(name):
    when_export = getattr(gui, name)

    assert isinstance(when_export, type)


@pytest.mark.parametrize("name", ["TTSService", "compute_backoff", "_compute_backoff"])
def test_tts_service_lazy_exports_are_resolved(name):
    when_export = getattr(tts, name)

    assert callable(when_export)


def test_tts_processor_is_the_sole_compatibility_projection():
    when_processor = tts.TTSProcessor

    assert when_processor.__bases__ == (TTSWorker,)
