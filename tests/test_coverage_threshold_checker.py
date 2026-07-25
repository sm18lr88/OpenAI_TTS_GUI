from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_coverage_thresholds.py"


def _report(
    path: Path,
    *,
    covered_lines: int = 91,
    statements: int = 100,
    covered_branches: int = 91,
    branches: int = 100,
    branch_coverage: bool = True,
    timestamp: str | None = None,
) -> None:
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    path.write_text(
        json.dumps(
            {
                "meta": {
                    "format": 3,
                    "version": "7.11.0",
                    "timestamp": timestamp,
                    "branch_coverage": branch_coverage,
                },
                "totals": {
                    "covered_lines": covered_lines,
                    "num_statements": statements,
                    "covered_branches": covered_branches,
                    "num_branches": branches,
                },
            }
        ),
        encoding="utf-8",
    )


def _run(report: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(report), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_checker_accepts_statement_and_branch_ratios_strictly_above_threshold(
    tmp_path: Path,
) -> None:
    # Given: both independently calculated ratios exceed their required minimum.
    report = tmp_path / "coverage.json"
    _report(report)

    # When: the report is checked through the command-line surface.
    result = _run(report)

    # Then: the gate succeeds and reports both independently measured ratios.
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "branches": 91.0,
        "minimum_branches_exclusive": 90.0,
        "minimum_statements_exclusive": 90.0,
        "statements": 91.0,
    }


def test_checker_rejects_ratio_equal_to_threshold(tmp_path: Path) -> None:
    # Given: combined coverage is high, but true branch coverage equals the strict floor.
    report = tmp_path / "coverage.json"
    _report(report, covered_lines=100, covered_branches=90)

    # When: the report is checked.
    result = _run(report)

    # Then: the independent branch gate fails rather than accepting equality.
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "error": "coverage_below_threshold",
        "failures": [{"actual": 90.0, "metric": "branches", "required_above": 90.0}],
    }


def test_checker_rejects_report_without_branch_measurement(tmp_path: Path) -> None:
    # Given: coverage.py produced a statement-only report.
    report = tmp_path / "coverage.json"
    _report(report, branch_coverage=False)

    # When: the report is checked.
    result = _run(report)

    # Then: malformed policy input is rejected distinctly from a threshold miss.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "invalid_coverage_report"}


def test_checker_rejects_backdated_report(tmp_path: Path) -> None:
    # Given: ratios pass, but the coverage.py report is decades old.
    report = tmp_path / "coverage.json"
    _report(report, timestamp="2000-01-01T00:00:00+00:00")

    # When: the report is checked through the command-line surface.
    result = _run(report)

    # Then: stale provenance is rejected independently of coverage ratios.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "stale_coverage_report"}


@pytest.mark.parametrize(
    ("timestamp", "expected_error"),
    [
        ("not-an-iso-timestamp", "invalid_coverage_report"),
        (
            (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            "future_coverage_report",
        ),
    ],
    ids=("invalid", "future"),
)
def test_checker_rejects_invalid_or_materially_future_timestamp(
    tmp_path: Path, timestamp: str, expected_error: str
) -> None:
    # Given: passing ratios paired with malformed or materially future report metadata.
    report = tmp_path / "coverage.json"
    _report(report, timestamp=timestamp)

    # When: the report is checked.
    result = _run(report)

    # Then: malformed and future-dated reports fail closed with distinct causes.
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": expected_error}


def test_checker_honors_explicit_thresholds(tmp_path: Path) -> None:
    # Given: coverage exceeds 90%, but not a caller's stricter branch requirement.
    report = tmp_path / "coverage.json"
    _report(report, covered_lines=96, covered_branches=94)

    # When: explicit independent thresholds are supplied.
    result = _run(report, "--min-statements", "95", "--min-branches", "95")

    # Then: only the failing metric is reported.
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "error": "coverage_below_threshold",
        "failures": [{"actual": 94.0, "metric": "branches", "required_above": 95.0}],
    }
