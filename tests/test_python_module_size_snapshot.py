from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_python_module_size.py"
REVISION = "55ebba7be4d833893d2872bb72ca3a48ac851977"


def run(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    root = path if path.is_dir() else path.parent
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
        [sys.executable, str(SCRIPT), str(path), *extra],
        check=False,
        capture_output=True,
        text=True,
    )


def test_size_snapshot_authenticates_baseline_and_requires_ratchet_baseline(tmp_path: Path) -> None:
    # Given: a known oversized file and its generated authenticated baseline.
    source = tmp_path / "source.py"
    source.write_text(
        "\n".join(f"item_{index} = {index}" for index in range(250)), encoding="utf-8"
    )
    baseline = tmp_path / "baseline.json"
    written = run(source, "--write-baseline", str(baseline))

    # When: valid, orphaned, and tampered ratchets are invoked.
    valid = run(source, "--baseline", str(baseline), "--fail-on-new-or-worsened")
    orphaned = run(source, "--fail-on-new-or-worsened")
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["source_revision"] = "0" * 40
    baseline.write_text(json.dumps(payload), encoding="utf-8")
    tampered = run(source, "--baseline", str(baseline), "--fail-on-new-or-worsened")

    # Then: exact debt passes only under a valid authenticated ratchet.
    assert written.returncode == 1
    assert valid.returncode == 0
    assert json.loads(orphaned.stdout) == {"error": "baseline_required"}
    assert json.loads(tampered.stdout) == {"error": "invalid_baseline"}


def test_size_snapshot_rejects_extra_malformed_and_bool_fields(tmp_path: Path) -> None:
    # Given: generated snapshots mutated into structurally invalid forms.
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    run(source, "--write-baseline", str(baseline))
    original = json.loads(baseline.read_text(encoding="utf-8"))

    # When: an extra key, malformed finding, and bool count are supplied.
    invalids = []
    extra = {**original, "unexpected": 1}
    invalids.append(extra)
    malformed = {**original, "findings": [{"path": "x"}]}
    invalids.append(malformed)
    boolean = {
        **original,
        "findings": [{"rule_id": "SIZE001", "path": "x", "count": True, "limit": 249}],
    }
    invalids.append(boolean)

    # Then: all malformed baselines fail with the same machine error.
    for invalid in invalids:
        baseline.write_text(json.dumps(invalid), encoding="utf-8")
        result = run(source, "--baseline", str(baseline), "--fail-on-new-or-worsened")
        assert json.loads(result.stdout) == {"error": "invalid_baseline"}
