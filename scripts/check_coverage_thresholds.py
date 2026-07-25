#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Generate a JSON report: uv run coverage json -o coverage.json
# 3. Run: uv run scripts/check_coverage_thresholds.py coverage.json
# ──────────────────
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal, TypedDict

DEFAULT_MINIMUM: Final = 90.0
MAXIMUM_REPORT_AGE: Final = timedelta(minutes=5)
MAXIMUM_FUTURE_REPORT_SKEW: Final = timedelta(minutes=2)
type Metric = Literal["statements", "branches"]
type ReportErrorCode = Literal[
    "future_coverage_report", "invalid_coverage_report", "stale_coverage_report"
]


@dataclass(frozen=True, slots=True)
class CoverageDocumentError(Exception):
    code: ReportErrorCode

    def __str__(self) -> str:
        return self.code


class FailurePayload(TypedDict):
    actual: float
    metric: Metric
    required_above: float


class SuccessPayload(TypedDict):
    branches: float
    minimum_branches_exclusive: float
    minimum_statements_exclusive: float
    statements: float


@dataclass(frozen=True, slots=True)
class CoverageTotals:
    covered_lines: int
    statements: int
    covered_branches: int
    branches: int

    @property
    def statement_percent(self) -> float:
        return self.covered_lines * 100.0 / self.statements

    @property
    def branch_percent(self) -> float:
        return self.covered_branches * 100.0 / self.branches


def _percentage(value: str) -> float:
    try:
        percentage = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid percentage: {value}") from error
    if not math.isfinite(percentage) or not 0.0 <= percentage < 100.0:
        raise argparse.ArgumentTypeError("percentage must be finite and in [0, 100)")
    return percentage


def _validate_timestamp(timestamp: str) -> None:
    try:
        report_time = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise CoverageDocumentError("invalid_coverage_report") from error
    report_time_utc = report_time.astimezone(UTC)
    current_time_utc = datetime.now(UTC)
    if current_time_utc - report_time_utc > MAXIMUM_REPORT_AGE:
        raise CoverageDocumentError("stale_coverage_report")
    if report_time_utc - current_time_utc > MAXIMUM_FUTURE_REPORT_SKEW:
        raise CoverageDocumentError("future_coverage_report")


def _parse_report(path: Path) -> CoverageTotals:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageDocumentError("invalid_coverage_report") from error
    match report:
        case {
            "meta": {"branch_coverage": True, "timestamp": str(timestamp)},
            "totals": {
                "covered_lines": int(covered_lines),
                "num_statements": int(statements),
                "covered_branches": int(covered_branches),
                "num_branches": int(branches),
            },
        }:
            values = (covered_lines, statements, covered_branches, branches)
            if any(type(value) is not int for value in values):
                raise CoverageDocumentError("invalid_coverage_report")
            if statements <= 0 or branches <= 0:
                raise CoverageDocumentError("invalid_coverage_report")
            if covered_lines < 0 or covered_lines > statements:
                raise CoverageDocumentError("invalid_coverage_report")
            if covered_branches < 0 or covered_branches > branches:
                raise CoverageDocumentError("invalid_coverage_report")
            _validate_timestamp(timestamp)
            return CoverageTotals(covered_lines, statements, covered_branches, branches)
        case _:
            raise CoverageDocumentError("invalid_coverage_report")


def _failures(
    totals: CoverageTotals, minimum_statements: float, minimum_branches: float
) -> list[FailurePayload]:
    failures: list[FailurePayload] = []
    if totals.statement_percent <= minimum_statements:
        failures.append(
            {
                "actual": totals.statement_percent,
                "metric": "statements",
                "required_above": minimum_statements,
            }
        )
    if totals.branch_percent <= minimum_branches:
        failures.append(
            {
                "actual": totals.branch_percent,
                "metric": "branches",
                "required_above": minimum_branches,
            }
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require separate statement and branch coverage thresholds."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-statements", type=_percentage, default=DEFAULT_MINIMUM)
    parser.add_argument("--min-branches", type=_percentage, default=DEFAULT_MINIMUM)
    args = parser.parse_args()
    try:
        totals = _parse_report(args.report)
    except CoverageDocumentError as error:
        print(json.dumps({"error": error.code}, sort_keys=True))
        return 2
    failures = _failures(totals, args.min_statements, args.min_branches)
    if failures:
        print(
            json.dumps({"error": "coverage_below_threshold", "failures": failures}, sort_keys=True)
        )
        return 1
    result: SuccessPayload = {
        "branches": totals.branch_percent,
        "minimum_branches_exclusive": args.min_branches,
        "minimum_statements_exclusive": args.min_statements,
        "statements": totals.statement_percent,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
