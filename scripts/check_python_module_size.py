#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tokenize
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Final

from python_contract_provenance import git_revision, source_hash, write_document

LIMIT: Final = 249
REVISION: Final = re.compile(r"^[0-9a-f]{40}$")
SEMANTIC_MODULES: Final[tuple[str, ...]] = (
    "check_python_module_size.py",
    "python_contract_provenance.py",
)
IGNORED: Final = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }
)
type SizePayload = dict[str, int | str]
type ReportPayload = dict[str, int | str | list[SizePayload]]


class SizeDocumentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SizeFinding:
    path: str
    count: int

    def payload(self) -> SizePayload:
        return {"rule_id": "SIZE001", "path": self.path, "count": self.count, "limit": LIMIT}


@dataclass(frozen=True, slots=True)
class SizeBaseline:
    source_revision: str
    semantics_sha256: str
    findings: tuple[SizeFinding, ...]
    snapshot_sha256: str

    def payload(self) -> ReportPayload:
        return {
            "version": 1,
            "limit": LIMIT,
            "source_revision": self.source_revision,
            "semantics_sha256": self.semantics_sha256,
            "findings": [finding.payload() for finding in self.findings],
            "snapshot_sha256": self.snapshot_sha256,
        }


def paths(values: list[str]) -> list[Path]:
    found: set[Path] = set()
    for value in values:
        path = Path(value).resolve()
        if not path.exists():
            raise SizeDocumentError
        if path.is_file() and path.suffix == ".py":
            found.add(path)
        elif path.is_dir():
            found.update(item.resolve() for item in path.rglob("*.py"))
        else:
            raise SizeDocumentError
    if not found:
        raise SizeDocumentError
    return sorted(found)


def pure_lines(path: Path) -> int:
    lines: set[int] = set()
    for token in tokenize.generate_tokens(StringIO(path.read_text(encoding="utf-8")).readline):
        if token.type not in IGNORED:
            lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines)


def inventory(files: list[Path], root: Path) -> list[SizeFinding]:
    return [
        SizeFinding(path.relative_to(root).as_posix(), count)
        for path in files
        if (count := pure_lines(path)) > LIMIT
    ]


def parse_baseline(path: Path) -> SizeBaseline:
    try:
        match json.loads(path.read_text(encoding="utf-8")):
            case {
                "version": 1,
                "limit": 249,
                "source_revision": str(revision),
                "semantics_sha256": str(semantics_hash),
                "findings": list(values),
                "snapshot_sha256": str(digest),
                **extra,
            } if not extra and REVISION.fullmatch(revision):
                findings: list[SizeFinding] = []
                for value in values:
                    match value:
                        case {
                            "rule_id": "SIZE001",
                            "path": str(file_path),
                            "count": int(count),
                            "limit": 249,
                            **extra,
                        } if not extra and not isinstance(count, bool):
                            findings.append(SizeFinding(file_path, count))
                            continue
                    raise SizeDocumentError
                baseline = SizeBaseline(revision, semantics_hash, tuple(findings), digest)
                if baseline.snapshot_sha256 == canonical_digest(baseline):
                    return baseline
    except (OSError, json.JSONDecodeError):
        pass
    raise SizeDocumentError


def canonical_digest(baseline: SizeBaseline) -> str:
    payload = baseline.payload()
    payload.pop("snapshot_sha256")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce the 249 pure Python LOC limit.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--fail-on-new-or-worsened", action="store_true")
    args = parser.parse_args()
    if args.fail_on_new_or_worsened and not args.baseline:
        print(json.dumps({"error": "baseline_required"}, sort_keys=True))
        return 2
    try:
        files = paths(args.paths)
    except SizeDocumentError:
        print(json.dumps({"error": "invalid_roots"}, sort_keys=True))
        return 2
    root = Path(os.path.commonpath([str(path.parent) for path in files])) if files else Path.cwd()
    try:
        current = inventory(files, root)
    except (OSError, UnicodeError, tokenize.TokenError):
        print(json.dumps({"error": "scan_failed"}, sort_keys=True))
        return 2
    semantics = source_hash(SEMANTIC_MODULES, Path(__file__).parent)
    if args.write_baseline:
        try:
            revision = git_revision(args.paths)
            if args.source_revision and args.source_revision != revision:
                raise SizeDocumentError
            unsigned = SizeBaseline(revision, semantics, tuple(current), "")
            baseline = SizeBaseline(revision, semantics, tuple(current), canonical_digest(unsigned))
            write_document(
                args.write_baseline,
                json.dumps(baseline.payload(), indent=2, sort_keys=True) + "\n",
            )
        except ValueError:
            print(json.dumps({"error": "invalid_generation"}, sort_keys=True))
            return 2
    findings = current
    baseline_count = 0
    if args.baseline and args.fail_on_new_or_worsened:
        try:
            parsed = parse_baseline(args.baseline)
            if parsed.semantics_sha256 != semantics:
                raise SizeDocumentError
            baseline_count = len(parsed.findings)
            expected = {finding.path: finding.count for finding in parsed.findings}
            findings = [
                finding for finding in current if finding.count > expected.get(finding.path, 0)
            ]
        except SizeDocumentError:
            print(json.dumps({"error": "invalid_baseline"}, sort_keys=True))
            return 2
    print(
        json.dumps(
            {
                "findings": [finding.payload() for finding in findings],
                "inventory": [finding.payload() for finding in current],
                "limit": LIMIT,
                "semantics_sha256": semantics,
                "current_count": len(current),
                "baseline_count": baseline_count,
            },
            sort_keys=True,
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
