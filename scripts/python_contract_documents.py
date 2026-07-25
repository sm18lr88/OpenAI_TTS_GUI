from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

type FindingPayload = dict[str, str | int]
type SnapshotPayload = dict[str, int | str | list[FindingPayload]]
REQUIRED: Final[frozenset[str]] = frozenset(
    {
        "ANY001",
        "OBJ001",
        "CAST001",
        "IGNORE001",
        "ERR001",
        "CATCH001",
        "DATA001",
        "VAR001",
        "QT001",
        "IMP001",
        "QTBRIDGE001",
    }
)
OBLIGATIONS: Final[dict[str, frozenset[str]]] = {
    "mutable_state": frozenset({"post_construction_field_mutation"}),
    "catch_boundary": frozenset({"typed_outcome", "log_and_domain_error"}),
}


class ContractDocumentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    path: str
    line: int
    fingerprint: str

    def payload(self) -> FindingPayload:
        return {
            "rule_id": self.rule_id,
            "path": self.path,
            "line": self.line,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class RuleDocument:
    version: int
    rules: frozenset[str]


@dataclass(frozen=True, slots=True)
class BoundaryEntry:
    path: str
    symbol: str
    kind: str
    rationale: str
    obligation: str | None


@dataclass(frozen=True, slots=True)
class BoundaryDocument:
    entries: tuple[BoundaryEntry, ...]


@dataclass(frozen=True, slots=True)
class Snapshot:
    version: int
    rules_sha256: str
    boundaries_sha256: str
    semantics_sha256: str
    source_revision: str
    findings: tuple[Finding, ...]
    snapshot_sha256: str

    def payload(self) -> SnapshotPayload:
        return {
            "version": self.version,
            "rules_sha256": self.rules_sha256,
            "boundaries_sha256": self.boundaries_sha256,
            "semantics_sha256": self.semantics_sha256,
            "source_revision": self.source_revision,
            "findings": [finding.payload() for finding in self.findings],
            "snapshot_sha256": self.snapshot_sha256,
        }


def parse_rules(path: Path) -> RuleDocument:
    try:
        match json.loads(path.read_text(encoding="utf-8")):
            case {"version": int(version), "rules": list(values), **extra} if (
                not extra and not isinstance(version, bool)
            ):
                rules: list[str] = []
                for value in values:
                    if not isinstance(value, str):
                        raise ContractDocumentError
                    rules.append(value)
                if len(rules) == len(REQUIRED) and frozenset(rules) == REQUIRED:
                    return RuleDocument(version, frozenset(rules))
    except (OSError, json.JSONDecodeError):
        pass
    raise ContractDocumentError


def parse_boundaries(path: Path) -> BoundaryDocument:
    try:
        match json.loads(path.read_text(encoding="utf-8")):
            case {"version": int(version), "entries": list(values), **extra} if (
                not extra and version == 1 and not isinstance(version, bool)
            ):
                entries: list[BoundaryEntry] = []
                for value in values:
                    match value:
                        case {
                            "path": str(file_path),
                            "symbol": str(symbol),
                            "kind": str(kind),
                            "rationale": str(rationale),
                            **extra,
                        } if (
                            set(extra) <= {"obligation"}
                            and kind in OBLIGATIONS
                            and rationale.strip()
                        ):
                            obligation = extra.get("obligation")
                            if isinstance(obligation, str) and obligation in OBLIGATIONS[kind]:
                                entries.append(
                                    BoundaryEntry(file_path, symbol, kind, rationale, obligation)
                                )
                                continue
                    raise ContractDocumentError
                return BoundaryDocument(tuple(entries))
    except (OSError, json.JSONDecodeError):
        pass
    raise ContractDocumentError


def parse_snapshot(path: Path) -> Snapshot:
    try:
        match json.loads(path.read_text(encoding="utf-8")):
            case {
                "version": int(version),
                "rules_sha256": str(rules_hash),
                "boundaries_sha256": str(boundaries_hash),
                "semantics_sha256": str(semantics_hash),
                "source_revision": str(revision),
                "findings": list(values),
                "snapshot_sha256": str(snapshot_hash),
                **extra,
            } if not extra and not isinstance(version, bool):
                findings: list[Finding] = []
                for value in values:
                    match value:
                        case {
                            "rule_id": str(rule_id),
                            "path": str(file_path),
                            "line": int(line),
                            "fingerprint": str(fingerprint),
                            **extra,
                        } if not extra and not isinstance(line, bool):
                            findings.append(Finding(rule_id, file_path, line, fingerprint))
                            continue
                    raise ContractDocumentError
                return Snapshot(
                    version,
                    rules_hash,
                    boundaries_hash,
                    semantics_hash,
                    revision,
                    tuple(findings),
                    snapshot_hash,
                )
    except (OSError, json.JSONDecodeError):
        pass
    raise ContractDocumentError
