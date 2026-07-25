from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    boundaries = root / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}\n', encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--rules",
            str(RULES),
            "--boundaries",
            str(boundaries),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _write(root: Path, relative_path: str, text: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _rule_ids(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {finding["rule_id"] for finding in json.loads(result.stdout)["findings"]}


def test_contract_checker_accepts_strict_module_and_runtime_qt_object(tmp_path: Path) -> None:
    # Given: annotation-safe code and a runtime Qt signal argument.
    _write(tmp_path, "ui.py", "from PyQt6.QtCore import pyqtSignal\nsignal = pyqtSignal(object)\n")

    # When: the checker scans the isolated root.
    result = _run(tmp_path)

    # Then: runtime object is not misclassified as an annotation violation.
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["findings"] == []


@pytest.mark.parametrize(
    ("relative_path", "source", "expected_rule"),
    [
        ("bad.py", "from typing import Any\ndef f(value: Any) -> None: pass\n", "ANY001"),
        ("bad.py", "def f(value: list[object]) -> None: pass\n", "OBJ001"),
        (
            "bad.py",
            "from typing import cast\ndef f(value: str) -> str: return cast(str, value)\n",
            "CAST001",
        ),
        ("bad.py", "value = 1  # type: ignore[attr-defined]\n", "IGNORE001"),
        ("bad.py", "raise ValueError('bad')\n", "ERR001"),
        ("bad.py", "try:\n    pass\nexcept Exception:\n    pass\n", "CATCH001"),
        ("bad.py", "from dataclasses import dataclass\n@dataclass\nclass State: pass\n", "DATA001"),
        (
            "bad.py",
            "if value == 1:\n    pass\nelif value == 2:\n    pass\nelif value == 3:\n    pass\n",
            "VAR001",
        ),
        ("src/openai_tts_gui/tts/new.py", "from PyQt6.QtCore import QObject\n", "QT001"),
        ("src/openai_tts_gui/tts/new.py", "from ..gui.workers import TTSWorker\n", "QTBRIDGE001"),
    ],
)
def test_contract_checker_rejects_each_direct_rule(
    tmp_path: Path, relative_path: str, source: str, expected_rule: str
) -> None:
    # Given: one representative violation in an isolated source tree.
    _write(tmp_path, relative_path, source)

    # When: the checker scans it.
    result = _run(tmp_path)

    # Then: the diagnostic is nonzero, JSON-only, and names the rule.
    assert result.returncode == 1
    assert _rule_ids(result) >= {expected_rule}
    assert "success" not in result.stdout.lower()


def test_contract_checker_enforces_facades_and_baseline_multiplicity(tmp_path: Path) -> None:
    # Given: a relocatable Any finding and an otherwise valid package facade.
    root = tmp_path / "root"
    _write(root, "src/openai_tts_gui/a/__init__.py", "")
    _write(root, "src/openai_tts_gui/b/__init__.py", "")
    _write(root, "src/openai_tts_gui/b/_private/__init__.py", "")
    _write(root, "src/openai_tts_gui/a/module.py", "from typing import Any\nx: Any\n")
    baseline = tmp_path / "baseline.json"
    for command in (
        ("git", "init"),
        ("git", "add", "."),
        (
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ),
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)

    # When: a baseline is written, then the same finding is relocated.
    first = _run(root, "--write-baseline", str(baseline))
    _write(root, "src/openai_tts_gui/a/module.py", "")
    _write(root, "src/openai_tts_gui/a/relocated.py", "from typing import Any\nx: Any\n")
    relocated = _run(root, "--baseline", str(baseline), "--fail-on-new-or-worsened")

    # Then: relocation passes, while duplication and cross-package deep imports fail.
    assert first.returncode == 1
    assert relocated.returncode == 0, relocated.stdout
    _write(root, "src/openai_tts_gui/a/duplicate.py", "from typing import Any\ny: Any\n")
    duplicated = _run(root, "--baseline", str(baseline), "--fail-on-new-or-worsened")
    _write(root, "src/openai_tts_gui/a/deep.py", "from openai_tts_gui.b._private import value\n")
    deep = _run(root)
    assert duplicated.returncode == 1
    assert "ANY001" in _rule_ids(duplicated)
    assert deep.returncode == 1
    assert "IMP001" in _rule_ids(deep)


def test_contract_checker_distinguishes_facade_exports_from_actual_deep_modules(
    tmp_path: Path,
) -> None:
    # Given: facade imports, a same-package private module, and actual cross-package modules.
    root = tmp_path / "root"
    _write(root, "src/openai_tts_gui/a/facade.py", "from openai_tts_gui.b import PublicSymbol\n")
    _write(root, "src/openai_tts_gui/a/deep.py", "from openai_tts_gui.b import _private\n")
    _write(root, "src/openai_tts_gui/b/_private.py", "")
    _write(root, "src/openai_tts_gui/b/local.py", "from openai_tts_gui.b import _private\n")
    _write(root, "src/openai_tts_gui/gui/workers.py", "")
    _write(root, "src/openai_tts_gui/tts/bad.py", "from openai_tts_gui.gui import workers\n")

    # When: `from package import name` targets are scanned with their sibling modules.
    result = _run(root)
    findings = json.loads(result.stdout)["findings"]
    import_paths = {item["path"] for item in findings if item["rule_id"] == "IMP001"}

    # Then: only physical cross-package modules are deep imports, including TTS-to-GUI.
    assert result.returncode == 1
    assert import_paths == {
        "src/openai_tts_gui/a/deep.py",
        "src/openai_tts_gui/tts/bad.py",
    }
    assert "QTBRIDGE001" in _rule_ids(result)


def test_contract_checker_rejects_invalid_rules_and_stale_boundary(tmp_path: Path) -> None:
    # Given: an isolated valid module plus malformed rules and stale boundaries.
    root = tmp_path / "root"
    _write(root, "valid.py", "answer: int = 42\n")
    bad_rules = tmp_path / "rules.json"
    valid_boundaries = tmp_path / "valid-boundaries.json"
    bad_boundaries = tmp_path / "boundaries.json"
    bad_rules.write_text("{", encoding="utf-8")
    valid_boundaries.write_text('{"version": 1, "entries": []}\n', encoding="utf-8")
    stale_entry = {
        "path": "valid.py",
        "symbol": "gone",
        "kind": "state_machine",
        "rationale": "test",
    }
    bad_boundaries.write_text(json.dumps({"entries": [stale_entry]}), encoding="utf-8")

    # When: malformed input and an unresolved boundary are supplied.
    malformed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--rules",
            str(bad_rules),
            "--boundaries",
            str(valid_boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    stale = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(root),
            "--rules",
            str(RULES),
            "--boundaries",
            str(bad_boundaries),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: both fail deterministically with machine-readable error records.
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["error"] == "invalid_rules"
    assert stale.returncode == 2
    assert json.loads(stale.stdout)["error"] == "invalid_boundaries"


@pytest.mark.parametrize(
    ("source", "detected"),
    [
        ("from contextlib import suppress as s\nwith s(Exception):\n    pass\n", True),
        ("import contextlib as c\nwith c.suppress(BaseException):\n    pass\n", True),
        ("from contextlib import suppress\nwith suppress(ValueError):\n    pass\n", False),
        (
            "def suppress(error: type[Exception]):\n    return error\n"
            "with suppress(Exception):\n    pass\n",
            False,
        ),
    ],
)
def test_contract_checker_resolves_broad_contextlib_suppress(
    tmp_path: Path, source: str, detected: bool
) -> None:
    # Given: imported, qualified, specific, or shadowed suppression.
    _write(tmp_path, "suppression.py", source)

    # When: the checker traverses suppression calls, including with items.
    result = _run(tmp_path)

    # Then: only resolved stdlib broad suppression is a broad handler.
    assert ("CATCH001" in _rule_ids(result)) is detected
