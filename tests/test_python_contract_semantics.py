from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"


def run(root: Path, boundaries: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
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


def test_contract_semantics_for_bridge_cast_and_boundary_obligation(tmp_path: Path) -> None:
    # Given: permitted and prohibited TTS edges plus cast Any and an invalid catch boundary.
    root = tmp_path / "src" / "openai_tts_gui"
    (root / "tts").mkdir(parents=True)
    (root / "gui").mkdir()
    (root / "tts" / "_compat.py").write_text(
        "from ..gui.workers import TTSWorker\n", encoding="utf-8"
    )
    (root / "tts" / "bad.py").write_text(
        "from typing import Any, cast\nx = cast(Any, 1)\nfrom ..gui.workers import TTSWorker\n",
        encoding="utf-8",
    )
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "path": "src/openai_tts_gui/tts/bad.py",
                        "symbol": "missing",
                        "kind": "catch_boundary",
                        "rationale": "x",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # When: the malformed boundary is supplied, then replaced with an empty manifest.
    invalid = run(tmp_path, boundaries)
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    findings = run(tmp_path, boundaries)

    # Then: schema obligations fail and only the unauthorized edge/cast are reported.
    assert invalid.returncode == 2
    assert json.loads(invalid.stdout) == {"error": "invalid_boundaries"}
    rules = {item["rule_id"] for item in json.loads(findings.stdout)["findings"]}
    assert findings.returncode == 1
    assert {"ANY001", "QTBRIDGE001"} <= rules


def test_contract_checker_reports_invalid_source(tmp_path: Path) -> None:
    # Given: syntactically invalid Python and a valid boundary manifest.
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")

    # When: the checker parses the source.
    result = run(tmp_path, boundaries)

    # Then: the source error is distinct from boundary validation.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_source"}


def test_lazy_compat_projection_passes_without_unrelated_boundary(tmp_path: Path) -> None:
    # Given: the sole permitted compatibility bridge and no unrelated boundary.
    root = tmp_path / "src" / "openai_tts_gui" / "tts"
    root.mkdir(parents=True)
    (root / "_compat.py").write_text(
        "from ..gui import TTSWorker\nclass TTSProcessor(TTSWorker): pass\n",
        encoding="utf-8",
    )
    (root / "__init__.py").write_text(
        "def __getattr__(name):\n"
        "    if name == 'TTSProcessor':\n"
        "        from ._compat import TTSProcessor\n"
        "        return TTSProcessor\n",
        encoding="utf-8",
    )
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")

    # When: the checker evaluates the shipped lazy projection shape.
    result = run(tmp_path, boundaries)

    # Then: the only allowed bridge introduces no findings.
    assert result.returncode == 0
    assert json.loads(result.stdout)["findings"] == []
    assert json.loads(result.stdout)["inventory"] == []


def test_relative_deep_import_is_inventory_checked(tmp_path: Path) -> None:
    # Given: a physical sibling package imported through a two-level relative import.
    root = tmp_path / "src" / "openai_tts_gui"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    (root / "a" / "consumer.py").write_text("from ..b import private\n", encoding="utf-8")
    (root / "b" / "private.py").write_text("", encoding="utf-8")
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")

    # When: the checker resolves the relative import against the module inventory.
    result = run(tmp_path, boundaries)

    # Then: the cross-package physical module is subject to IMP001.
    assert "IMP001" in {item["rule_id"] for item in json.loads(result.stdout)["findings"]}
