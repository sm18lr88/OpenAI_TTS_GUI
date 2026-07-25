from __future__ import annotations

import hashlib
import json
import re

from python_contract_documents import ContractDocumentError, Finding, Snapshot

REVISION = re.compile(r"^[0-9a-f]{40}$")


def digest(snapshot: Snapshot) -> str:
    payload = snapshot.payload()
    payload.pop("snapshot_sha256")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def manifest(
    inventory: list[Finding],
    rules_hash: str,
    boundaries_hash: str,
    semantics_hash: str,
    revision: str,
) -> Snapshot:
    if not REVISION.fullmatch(revision):
        raise ContractDocumentError
    unsigned = Snapshot(
        2, rules_hash, boundaries_hash, semantics_hash, revision, tuple(inventory), ""
    )
    return Snapshot(
        2, rules_hash, boundaries_hash, semantics_hash, revision, tuple(inventory), digest(unsigned)
    )


def validate(
    snapshot: Snapshot, rules_hash: str, boundaries_hash: str, semantics_hash: str
) -> None:
    if (
        snapshot.version != 2
        or snapshot.rules_sha256 != rules_hash
        or snapshot.boundaries_sha256 != boundaries_hash
        or snapshot.semantics_sha256 != semantics_hash
        or not REVISION.fullmatch(snapshot.source_revision)
    ):
        raise ContractDocumentError
    if snapshot.snapshot_sha256 != digest(
        Snapshot(
            snapshot.version,
            snapshot.rules_sha256,
            snapshot.boundaries_sha256,
            snapshot.semantics_sha256,
            snapshot.source_revision,
            snapshot.findings,
            "",
        )
    ):
        raise ContractDocumentError


def worsened(inventory: list[Finding], snapshot: Snapshot) -> list[Finding]:
    baseline: dict[tuple[str, str], list[Finding]] = {}
    current: dict[tuple[str, str], list[Finding]] = {}
    for finding in snapshot.findings:
        baseline.setdefault((finding.rule_id, finding.fingerprint), []).append(finding)
    for finding in inventory:
        current.setdefault((finding.rule_id, finding.fingerprint), []).append(finding)
    excess: list[Finding] = []
    for key, findings in current.items():
        remaining = sorted(baseline.get(key, []), key=lambda item: (item.path, item.line))
        unmatched: list[Finding] = []
        for finding in sorted(findings, key=lambda item: (item.path, item.line)):
            exact = next(
                (
                    item
                    for item in remaining
                    if item.path == finding.path and item.line == finding.line
                ),
                None,
            )
            if exact is None:
                unmatched.append(finding)
            else:
                remaining.remove(exact)
        excess.extend(unmatched[len(remaining) :])
    return sorted(excess, key=lambda item: (item.rule_id, item.path, item.line, item.fingerprint))
