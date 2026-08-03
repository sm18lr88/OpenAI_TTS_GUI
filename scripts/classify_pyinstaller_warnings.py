from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import TypedDict

POLICY_VERSION = 3
SOURCE_FILES = (
    "pyproject.toml",
    "packaging/pyinstaller/openai_tts.spec",
    "scripts/pyinstaller_entry.py",
)
TERMINAL_CATEGORIES = (
    (
        "pydantic-v1-python-3.14",
        "Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    ),
    ("tzdata-hidden-import", 'Hidden import "tzdata" not found!'),
)
MISSING_MODULE = re.compile(r"^(?:missing|excluded) module named .+ - imported by .+$")


class PolicyError(Exception):
    pass


class ExpectedTerminal(TypedDict):
    category: str
    required_count: int
    signature: str


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze and classify PyInstaller warning records.")
    policy = parser.add_mutually_exclusive_group(required=True)
    policy.add_argument("--policy", type=Path)
    policy.add_argument("--write-policy", type=Path)
    parser.add_argument("--terminal-log", type=Path, required=True)
    parser.add_argument("--warn-file", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity(source_root: Path) -> dict[str, str]:
    missing = [relative for relative in SOURCE_FILES if not (source_root / relative).is_file()]
    if missing:
        raise PolicyError(f"source identity files missing: {', '.join(missing)}")
    return {relative: _sha256_file(source_root / relative) for relative in SOURCE_FILES}


def _terminal_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if "WARNING:" in line or "UserWarning:" in line
    ]


def _missing_module_records(path: Path) -> list[str]:
    records: dict[str, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = line.strip()
        if MISSING_MODULE.fullmatch(record):
            module, _, importer_text = record.partition(" - imported by ")
            records.setdefault(module, set()).update(_importers(importer_text))
    return [
        f"{module} - imported by {', '.join(sorted(importers))}"
        for module, importers in sorted(records.items())
    ]


def _importers(value: str) -> list[str]:
    importers: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            importers.append(value[start:index].strip())
            start = index + 1
    importers.append(value[start:].strip())
    return importers


def _not_before(arguments: argparse.Namespace) -> int:
    return int(min(arguments.terminal_log.stat().st_mtime, arguments.warn_file.stat().st_mtime))


def _freeze_policy(arguments: argparse.Namespace, terminal: list[str], records: list[str]) -> None:
    categories = []
    for category, signature in TERMINAL_CATEGORIES:
        count = sum(signature in line for line in terminal)
        if count == 0:
            raise PolicyError(f"missing expected category: {category}")
        categories.append({"category": category, "required_count": count, "signature": signature})
    policy = {
        "expected_missing_records": sorted(records),
        "expected_terminal": categories,
        "not_before_unix_seconds": _not_before(arguments),
        "source_identity": _source_identity(arguments.source_root),
        "version": POLICY_VERSION,
    }
    arguments.write_policy.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_policy(path: Path) -> tuple[int, dict[str, str], list[ExpectedTerminal], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "expected_missing_records",
        "expected_terminal",
        "not_before_unix_seconds",
        "source_identity",
        "version",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or payload["version"] != POLICY_VERSION
    ):
        raise PolicyError("invalid policy schema or version")
    records = payload["expected_missing_records"]
    terminal = payload["expected_terminal"]
    not_before = payload["not_before_unix_seconds"]
    source_identity = payload["source_identity"]
    if not isinstance(records, list) or not all(isinstance(record, str) for record in records):
        raise PolicyError("invalid missing-record policy")
    if not isinstance(terminal, list):
        raise PolicyError("invalid terminal-warning policy")
    typed_terminal: list[ExpectedTerminal] = []
    for category in terminal:
        if not isinstance(category, dict):
            raise PolicyError("invalid terminal-warning policy")
        if set(category) != {"category", "required_count", "signature"}:
            raise PolicyError("invalid terminal-warning policy")
        if not isinstance(category["category"], str) or not isinstance(category["signature"], str):
            raise PolicyError("invalid terminal-warning policy")
        if not isinstance(category["required_count"], int):
            raise PolicyError("invalid terminal-warning policy")
        typed_terminal.append(
            {
                "category": category["category"],
                "required_count": category["required_count"],
                "signature": category["signature"],
            }
        )
    if not isinstance(not_before, int):
        raise PolicyError("invalid policy freshness")
    if not isinstance(source_identity, dict) or set(source_identity) != set(SOURCE_FILES):
        raise PolicyError("invalid policy source identity")
    source_values_are_strings = all(
        isinstance(name, str) and isinstance(value, str) for name, value in source_identity.items()
    )
    if not source_values_are_strings:
        raise PolicyError("invalid policy source identity")
    return not_before, source_identity, typed_terminal, records


def _classify_terminal(
    lines: list[str], expected: list[ExpectedTerminal]
) -> tuple[list[dict[str, str]], list[str]]:
    classified: list[dict[str, str]] = []
    unknown: list[str] = []
    for line in lines:
        match = next((item for item in expected if item["signature"] in line), None)
        if match is None:
            unknown.append(line)
        else:
            classified.append({"category": str(match["category"]), "line": line})
    return classified, unknown


def _required_category_errors(
    expected: list[ExpectedTerminal], classified: list[dict[str, str]]
) -> list[str]:
    return [
        f"missing expected category: {item['category']}"
        for item in expected
        if sum(entry["category"] == item["category"] for entry in classified)
        < item["required_count"]
    ]


def main() -> int:
    arguments = _parse_arguments()
    terminal = _terminal_lines(arguments.terminal_log)
    records = _missing_module_records(arguments.warn_file)
    if arguments.write_policy is not None:
        try:
            _freeze_policy(arguments, terminal, records)
        except PolicyError as error:
            report = {"errors": [str(error)], "status": "failed"}
            arguments.report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps(report, sort_keys=True))
            return 1
        report = {"missing_module_records": records, "status": "frozen", "terminal": terminal}
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    try:
        not_before, source_identity, expected_terminal, expected_records = _load_policy(
            arguments.policy
        )
    except (OSError, PolicyError, json.JSONDecodeError) as error:
        report = {"errors": [f"invalid policy: {error}"], "status": "failed"}
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))
        return 1
    expected, unknown = _classify_terminal(terminal, expected_terminal)
    errors = _required_category_errors(expected_terminal, expected)
    if source_identity != _source_identity(arguments.source_root):
        errors.append("source identity differs from policy")
    if int(arguments.terminal_log.stat().st_mtime) < not_before:
        errors.append(f"stale evidence: {arguments.terminal_log}")
    if int(arguments.warn_file.stat().st_mtime) < not_before:
        errors.append(f"stale evidence: {arguments.warn_file}")
    expected_record_set = set(expected_records)
    unknown.extend(record for record in records if record not in expected_record_set)
    errors.extend(
        f"missing expected warning record: {record}"
        for record in expected_record_set - set(records)
    )
    errors.extend(f"unknown warning: {line}" for line in unknown)
    report = {
        "expected": expected,
        "errors": errors,
        "missing_module_records": records,
        "status": "ok" if not errors else "failed",
        "unknown": unknown,
    }
    arguments.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
