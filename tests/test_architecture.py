"""Architecture boundary tests.

These tests verify that the planned module boundaries do NOT import PyQt6,
enforcing separation of concerns between UI and business logic layers.

All tests are marked xfail because the target modules do not yet exist.
Once the architecture upgrade creates those modules, these tests should pass
and the xfail markers should be removed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Source root: tests/ is one level below the repo root, src/ is a sibling.
_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "openai_tts_gui"


def _has_pyqt6_import(filepath: Path) -> bool:
    """Check if a Python file imports from PyQt6."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "PyQt6" in node.module:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "PyQt6" in alias.name:
                    return True
    return False


def _check_dir_no_pyqt6(dirpath: Path) -> list[str]:
    """Return list of filenames in dirpath that import PyQt6."""
    violators = []
    for py_file in sorted(dirpath.glob("*.py")):
        if _has_pyqt6_import(py_file):
            violators.append(py_file.name)
    return violators


@pytest.mark.xfail(reason="Module not yet created: src/openai_tts_gui/config/settings.py")
def test_config_settings_no_qt_imports():
    """config/settings.py must not import PyQt6 (pure-data config layer)."""
    target = _SRC_ROOT / "config" / "settings.py"
    assert target.exists(), f"Expected module not found: {target}"
    assert not _has_pyqt6_import(target), (
        f"{target.name} must not import PyQt6 — config is a UI-free layer"
    )


@pytest.mark.xfail(reason="Module not yet created: src/openai_tts_gui/core/")
def test_core_modules_no_qt_imports():
    """All files under core/ must not import PyQt6 (pure-logic layer)."""
    core_dir = _SRC_ROOT / "core"
    assert core_dir.is_dir(), f"Expected directory not found: {core_dir}"
    violators = _check_dir_no_pyqt6(core_dir)
    assert not violators, f"core/ files that incorrectly import PyQt6: {violators}"


@pytest.mark.xfail(reason="Module not yet created: src/openai_tts_gui/tts/_service.py")
def test_tts_service_no_qt_imports():
    """tts/_service.py must not import PyQt6 (pure-logic TTS layer)."""
    target = _SRC_ROOT / "tts" / "_service.py"
    assert target.exists(), f"Expected module not found: {target}"
    assert not _has_pyqt6_import(target), (
        f"{target.name} must not import PyQt6 — TTS service is a UI-free layer"
    )


@pytest.mark.xfail(reason="Module not yet created: src/openai_tts_gui/keystore/")
def test_keystore_no_qt_imports():
    """All files under keystore/ must not import PyQt6."""
    keystore_dir = _SRC_ROOT / "keystore"
    assert keystore_dir.is_dir(), f"Expected directory not found: {keystore_dir}"
    violators = _check_dir_no_pyqt6(keystore_dir)
    assert not violators, f"keystore/ files that incorrectly import PyQt6: {violators}"


@pytest.mark.xfail(reason="Module not yet created: src/openai_tts_gui/presets/")
def test_presets_no_qt_imports():
    """All files under presets/ must not import PyQt6."""
    presets_dir = _SRC_ROOT / "presets"
    assert presets_dir.is_dir(), f"Expected directory not found: {presets_dir}"
    violators = _check_dir_no_pyqt6(presets_dir)
    assert not violators, f"presets/ files that incorrectly import PyQt6: {violators}"
