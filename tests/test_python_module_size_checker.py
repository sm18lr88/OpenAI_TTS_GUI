from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_module_size.py"


def _run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(path) for path in paths)],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_module(root: Path, pure_lines: int) -> Path:
    module = root / "fixture.py"
    content = "\n".join(f"value_{index} = {index}" for index in range(pure_lines))
    module.write_text(content, encoding="utf-8")
    return module


def test_size_checker_accepts_exactly_249_pure_lines(tmp_path: Path) -> None:
    # Given: a module with exactly the permitted number of meaningful tokens.
    module = _write_module(tmp_path, 249)

    # When: the repository checker scans it.
    result = _run(module)

    # Then: it emits deterministic JSON and accepts the module.
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["findings"] == []


def test_size_checker_rejects_250_pure_lines_with_actionable_json(tmp_path: Path) -> None:
    # Given: a module one pure line above the maximum.
    module = _write_module(tmp_path, 250)

    # When: the repository checker scans it.
    result = _run(module)

    # Then: failure identifies the path, count, maximum, and stable rule ID.
    assert result.returncode == 1
    finding = json.loads(result.stdout)["findings"][0]
    assert finding == {
        "count": 250,
        "limit": 249,
        "path": "fixture.py",
        "rule_id": "SIZE001",
    }
