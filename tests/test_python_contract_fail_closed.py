from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "check_python_contracts.py"
SIZE = ROOT / "scripts" / "check_python_module_size.py"
RULES = ROOT / "quality" / "python" / "rules.json"


def execute(
    script: Path, root: Path, boundaries: Path | None = None
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script), str(root)]
    if boundaries is not None:
        command.extend(["--rules", str(RULES), "--boundaries", str(boundaries)])
    return subprocess.run(command, check=False, capture_output=True, text=True)


@pytest.mark.parametrize("script", [CONTRACT, SIZE])
def test_checkers_reject_nonexistent_and_empty_roots(tmp_path: Path, script: Path) -> None:
    # Given: a missing root and a directory containing no Python files.
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}', encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()

    # When: each root is scanned.
    # Then: both cases fail closed with machine-readable JSON.
    for root in (tmp_path / "missing", empty):
        result = execute(script, root, boundaries if script == CONTRACT else None)
        assert result.returncode == 2
        assert json.loads(result.stdout)["error"] == "invalid_roots"


@pytest.mark.parametrize(
    "entry",
    [
        {"path": "missing.py", "symbol": "x", "kind": "mutable_state", "rationale": "x"},
        {"path": "sample.py", "symbol": "sample.State", "kind": "unknown", "rationale": "x"},
        {"path": "sample.py", "symbol": "sample.State", "kind": "mutable_state", "rationale": ""},
    ],
)
def test_boundaries_are_closed_schema_and_exact_owner(
    tmp_path: Path, entry: dict[str, str]
) -> None:
    # Given: a malformed, stale, or structurally unjustified boundary declaration.
    sample = tmp_path / "sample.py"
    boundaries = tmp_path / "boundaries.json"
    sample.write_text("class State: pass\n", encoding="utf-8")
    boundaries.write_text(json.dumps({"version": 1, "entries": [entry]}), encoding="utf-8")

    # When: the contract checker validates boundaries.
    # Then: it rejects the manifest rather than allowing a generic exemption.
    result = execute(CONTRACT, sample, boundaries)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_boundaries"}


@pytest.mark.parametrize(
    "document",
    [
        {"entries": []},
        {"version": True, "entries": []},
        {"version": 2, "entries": []},
        {"version": "1", "entries": []},
        {"version": 1, "entries": [], "unexpected": True},
    ],
)
def test_boundaries_require_exact_version_one_schema(
    tmp_path: Path, document: dict[str, bool | int | str | list[str]]
) -> None:
    sample = tmp_path / "sample.py"
    boundaries = tmp_path / "boundaries.json"
    sample.write_text("value: int = 1\n", encoding="utf-8")
    boundaries.write_text(json.dumps(document), encoding="utf-8")

    result = execute(CONTRACT, sample, boundaries)

    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_boundaries"}
