from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"
SOURCE = ROOT / "src"

ALLOWED_MODULES = (
    "openai_tts_gui.cli",
    "openai_tts_gui.config.app_settings",
    "openai_tts_gui.config.settings",
    "openai_tts_gui.core",
    "openai_tts_gui.core.audio",
    "openai_tts_gui.core.ffmpeg",
    "openai_tts_gui.core.metadata",
    "openai_tts_gui.core.text",
    "openai_tts_gui.keystore",
    "openai_tts_gui.keystore._crypto",
    "openai_tts_gui.keystore._storage",
    "openai_tts_gui.presets",
    "openai_tts_gui.presets._storage",
    "openai_tts_gui.tts",
    "openai_tts_gui.tts._service",
)


def _write(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _check(root: Path) -> list[dict[str, str]]:
    boundaries = root / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--rules",
            str(RULES),
            "--boundaries",
            str(boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    return json.loads(result.stdout)["findings"]


def test_contract_checker_distinguishes_file_modules_package_modules_and_facades(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    _write(root, "src/openai_tts_gui/a/facade.py", "from openai_tts_gui.b import PublicSymbol\n")
    _write(
        root,
        "src/openai_tts_gui/a/direct_deep.py",
        "from openai_tts_gui.b._package import PublicSymbol\n",
    )
    _write(root, "src/openai_tts_gui/a/private_file.py", "from openai_tts_gui.b import _file\n")
    _write(
        root,
        "src/openai_tts_gui/a/private_package.py",
        "from openai_tts_gui.b import _package\n",
    )
    _write(root, "src/openai_tts_gui/b/__init__.py", "")
    _write(root, "src/openai_tts_gui/b/_file.py", "")
    _write(root, "src/openai_tts_gui/b/_package/__init__.py", "")
    _write(root, "src/openai_tts_gui/b/local.py", "from openai_tts_gui.b import _file\n")
    _write(root, "src/openai_tts_gui/gui/workers.py", "")
    _write(root, "src/openai_tts_gui/tts/bad.py", "from openai_tts_gui.gui import workers\n")

    findings = _check(root)
    import_paths = {item["path"] for item in findings if item["rule_id"] == "IMP001"}
    rule_ids = {item["rule_id"] for item in findings}

    assert import_paths == {
        "src/openai_tts_gui/a/direct_deep.py",
        "src/openai_tts_gui/a/private_file.py",
        "src/openai_tts_gui/a/private_package.py",
        "src/openai_tts_gui/tts/bad.py",
    }
    assert "QTBRIDGE001" in rule_ids


def test_qt_import_is_rejected_in_every_protected_path(tmp_path: Path) -> None:
    # Given: one direct PyQt6 import in each protected module category.
    root = tmp_path / "root"
    protected = (
        "src/openai_tts_gui/core/new.py",
        "src/openai_tts_gui/tts/new.py",
        "src/openai_tts_gui/keystore/new.py",
        "src/openai_tts_gui/presets/new.py",
        "src/openai_tts_gui/config/settings.py",
        "src/openai_tts_gui/config/app_settings.py",
    )
    for path in protected:
        _write(root, path, "from PyQt6.QtCore import QObject\n")

    # When: the checker scans the synthetic repository.
    findings = _check(root)

    # Then: every protected import is a QT001 finding at its exact repository path.
    assert {item["path"] for item in findings if item["rule_id"] == "QT001"} == set(protected)


def test_protected_modules_import_without_pyqt6_but_processor_bridge_is_denied() -> None:
    code = """
import importlib
import importlib.abc
import json
import sys
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from types import ModuleType

class DenyPyQt6(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname == "PyQt6" or fullname.startswith("PyQt6."):
            raise ModuleNotFoundError("PyQt6 denied by boundary probe")
        return None

sys.meta_path.insert(0, DenyPyQt6())
outcomes = {}
for module_name in json.loads(sys.argv[1]):
    try:
        importlib.import_module(module_name)
    except Exception as error:
        outcomes[module_name] = f"{type(error).__name__}: {error}"
    else:
        outcomes[module_name] = "ok"

try:
    from openai_tts_gui.tts import TTSProcessor
except ModuleNotFoundError as error:
    processor = {"message": str(error), "type": type(error).__name__}
else:
    processor = {"message": TTSProcessor.__name__, "type": "available"}

print(json.dumps({"allowed": outcomes, "processor": processor}, sort_keys=True))
"""
    environment = os.environ | {"PYTHONPATH": str(SOURCE)}
    result = subprocess.run(
        [sys.executable, "-c", code, json.dumps(ALLOWED_MODULES)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "allowed": {module_name: "ok" for module_name in ALLOWED_MODULES},
        "processor": {
            "message": "PyQt6 denied by boundary probe",
            "type": "ModuleNotFoundError",
        },
    }
