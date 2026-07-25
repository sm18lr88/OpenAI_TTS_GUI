from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_contracts.py"
RULES = ROOT / "quality" / "python" / "rules.json"
REVISION = "55ebba7be4d833893d2872bb72ca3a48ac851977"


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    boundaries = root / "boundaries.json"
    boundaries.write_text('{"version": 1, "entries": []}\n', encoding="utf-8")
    if "--write-baseline" in extra and not (root / ".git").exists():
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


def test_baseline_becomes_strict_only_when_ratchet_flag_is_requested(tmp_path: Path) -> None:
    # Given: a baseline with one known finding.
    source = tmp_path / "source.py"
    source.write_text("from typing import Any\nvalue: Any\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    _run(tmp_path, "--write-baseline", str(baseline))

    # When: the baseline is checked with and without the strict ratchet flag.
    complete = _run(tmp_path, "--baseline", str(baseline))
    ratcheted = _run(tmp_path, "--baseline", str(baseline), "--fail-on-new-or-worsened")

    # Then: unflagged mode emits complete inventory, while ratchet mode permits exact debt.
    assert complete.returncode == 1
    assert json.loads(complete.stdout)["findings"]
    assert ratcheted.returncode == 0


def test_snapshot_rejects_tampered_provenance_and_requires_baseline_for_ratchet(
    tmp_path: Path,
) -> None:
    # Given: a valid serialized snapshot whose provenance is altered after creation.
    source = tmp_path / "source.py"
    source.write_text("from typing import Any\nvalue: Any\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    _run(tmp_path, "--write-baseline", str(baseline))
    snapshot = json.loads(baseline.read_text(encoding="utf-8"))
    snapshot["source_revision"] = "0" * 40
    baseline.write_text(json.dumps(snapshot), encoding="utf-8")

    # When: the altered snapshot and an orphan ratchet flag are used.
    tampered = _run(tmp_path, "--baseline", str(baseline), "--fail-on-new-or-worsened")
    orphaned = _run(tmp_path, "--fail-on-new-or-worsened")

    # Then: both fail as machine-readable invalid configurations.
    assert tampered.returncode == 2
    assert json.loads(tampered.stdout)["error"] == "invalid_baseline"
    assert orphaned.returncode == 2
    assert json.loads(orphaned.stdout)["error"] == "baseline_required"


def test_ratchet_reports_duplicate_excess_and_allows_relocation(tmp_path: Path) -> None:
    # Given: two baseline files with identical annotation findings.
    source = "from typing import Any\nvalue: Any\n"
    old_a = tmp_path / "old_a.py"
    old_b = tmp_path / "old_b.py"
    old_a.write_text(source, encoding="utf-8")
    old_b.write_text(source, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    _run(tmp_path, "--write-baseline", str(baseline))

    # When: a duplicate is added, then one historical occurrence relocates.
    new_c = tmp_path / "new_c.py"
    new_c.write_text(source, encoding="utf-8")
    duplicate = _run(tmp_path, "--baseline", str(baseline), "--fail-on-new-or-worsened")
    new_c.unlink()
    old_a.unlink()
    relocated = tmp_path / "relocated.py"
    relocated.write_text(source, encoding="utf-8")
    relocation = _run(tmp_path, "--baseline", str(baseline), "--fail-on-new-or-worsened")

    # Then: only the added path is actionable, while relocation is allowed.
    assert duplicate.returncode == 1
    findings = json.loads(duplicate.stdout)["findings"]
    assert [finding["path"] for finding in findings] == ["new_c.py"]
    assert relocation.returncode == 0
