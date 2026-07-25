from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

# Source root: tests/ is one level below the repo root, src/ is a sibling.
_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "openai_tts_gui"
_ROOT = _SRC_ROOT.parents[1]
_CONTRACT_CHECKER = _ROOT / "scripts" / "check_python_contracts.py"
_CONTRACT_RULES = _ROOT / "quality" / "python" / "rules.json"
_CONTRACT_BOUNDARIES = _ROOT / "quality" / "python" / "boundaries.json"
_PROTECTED_QT_FREE_DIRECTORIES = ("core", "keystore", "presets")
_PROTECTED_TTS_MODULES = tuple(
    path for path in sorted((_SRC_ROOT / "tts").glob("*.py")) if path.name != "_compat.py"
)


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
    for py_file in sorted(dirpath.rglob("*.py")):
        if _has_pyqt6_import(py_file):
            violators.append(py_file.relative_to(dirpath).as_posix())
    return violators


def test_config_settings_no_qt_imports():
    """config/settings.py must not import PyQt6 (pure-data config layer)."""
    target = _SRC_ROOT / "config" / "settings.py"
    assert target.exists(), f"Expected module not found: {target}"
    assert not _has_pyqt6_import(target), (
        f"{target.name} must not import PyQt6 — config is a UI-free layer"
    )


def test_core_modules_no_qt_imports():
    """All files under core/ must not import PyQt6 (pure-logic layer)."""
    core_dir = _SRC_ROOT / "core"
    assert core_dir.is_dir(), f"Expected directory not found: {core_dir}"
    violators = _check_dir_no_pyqt6(core_dir)
    assert not violators, f"core/ files that incorrectly import PyQt6: {violators}"


def test_tts_service_no_qt_imports():
    """tts/_service.py must not import PyQt6 (pure-logic TTS layer)."""
    target = _SRC_ROOT / "tts" / "_service.py"
    assert target.exists(), f"Expected module not found: {target}"
    assert not _has_pyqt6_import(target), (
        f"{target.name} must not import PyQt6 — TTS service is a UI-free layer"
    )


def test_keystore_no_qt_imports():
    """All files under keystore/ must not import PyQt6."""
    keystore_dir = _SRC_ROOT / "keystore"
    assert keystore_dir.is_dir(), f"Expected directory not found: {keystore_dir}"
    violators = _check_dir_no_pyqt6(keystore_dir)
    assert not violators, f"keystore/ files that incorrectly import PyQt6: {violators}"


def test_presets_no_qt_imports():
    """All files under presets/ must not import PyQt6."""
    presets_dir = _SRC_ROOT / "presets"
    assert presets_dir.is_dir(), f"Expected directory not found: {presets_dir}"
    violators = _check_dir_no_pyqt6(presets_dir)
    assert not violators, f"presets/ files that incorrectly import PyQt6: {violators}"


def test_declared_qt_free_modules_enumerate_every_python_file() -> None:
    targets = [
        *(
            path
            for directory in _PROTECTED_QT_FREE_DIRECTORIES
            for path in sorted((_SRC_ROOT / directory).rglob("*.py"))
        ),
        *_PROTECTED_TTS_MODULES,
        _SRC_ROOT / "config" / "settings.py",
        _SRC_ROOT / "config" / "app_settings.py",
    ]

    assert targets
    assert not [
        path.relative_to(_SRC_ROOT).as_posix() for path in targets if _has_pyqt6_import(path)
    ]


def test_repository_contract_gate_enforces_qt_bridge_and_facade_rules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_CONTRACT_CHECKER),
            "src/openai_tts_gui",
            "tests",
            "scripts",
            "--rules",
            str(_CONTRACT_RULES),
            "--boundaries",
            str(_CONTRACT_BOUNDARIES),
        ],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0, payload
    assert payload["findings"] == []
    assert payload["inventory"] == []
