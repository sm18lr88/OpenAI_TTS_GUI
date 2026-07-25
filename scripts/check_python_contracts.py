#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import tokenize
from pathlib import Path

from python_contract_documents import (
    REQUIRED,
    ContractDocumentError,
    parse_boundaries,
    parse_rules,
    parse_snapshot,
)
from python_contract_inventory import boundaries, files, module_inventory, root, scan
from python_contract_provenance import (
    canonical_hash,
    contract_modules,
    git_revision,
    source_hash,
    write_document,
)
from python_contract_snapshot import manifest, validate, worsened


def main() -> int:
    parser = argparse.ArgumentParser(description="Check strict Python contracts.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--boundaries", required=True, type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--fail-on-new-or-worsened", action="store_true")
    args = parser.parse_args()
    if args.fail_on_new_or_worsened and not args.baseline:
        print(json.dumps({"error": "baseline_required"}, sort_keys=True))
        return 2
    try:
        rules = parse_rules(args.rules)
        if rules.version != 1 or rules.rules != REQUIRED:
            raise ContractDocumentError
    except (ContractDocumentError, ValueError):
        print(json.dumps({"error": "invalid_rules"}, sort_keys=True))
        return 2
    try:
        paths = files(args.paths)
    except ContractDocumentError:
        print(json.dumps({"error": "invalid_roots"}, sort_keys=True))
        return 2
    try:
        declared = boundaries(parse_boundaries(args.boundaries), paths)
        root_path = root(paths)
        modules = module_inventory(paths)
        inventory = [
            finding for path in paths for finding in scan(path, root_path, declared, modules)
        ]
    except (ContractDocumentError, ValueError):
        print(json.dumps({"error": "invalid_boundaries"}, sort_keys=True))
        return 2
    except (SyntaxError, UnicodeError, tokenize.TokenError):
        print(json.dumps({"error": "invalid_source"}, sort_keys=True))
        return 2
    inventory.sort(key=lambda item: (item.rule_id, item.path, item.line, item.fingerprint))
    try:
        rules_hash = canonical_hash(args.rules)
        boundaries_hash = canonical_hash(args.boundaries)
        semantics_hash = source_hash(contract_modules(Path(__file__).parent), Path(__file__).parent)
    except ContractDocumentError:
        print(json.dumps({"error": "invalid_rules"}, sort_keys=True))
        return 2
    if args.write_baseline:
        try:
            revision = git_revision(args.paths)
            if args.source_revision and args.source_revision != revision:
                raise ContractDocumentError
            snapshot = manifest(inventory, rules_hash, boundaries_hash, semantics_hash, revision)
            write_document(
                args.write_baseline,
                json.dumps(snapshot.payload(), indent=2, sort_keys=True) + "\n",
            )
        except ContractDocumentError:
            print(json.dumps({"error": "invalid_generation"}, sort_keys=True))
            return 2
    findings = inventory
    baseline_count = 0
    if args.baseline and args.fail_on_new_or_worsened:
        try:
            baseline = parse_snapshot(args.baseline)
            validate(baseline, rules_hash, boundaries_hash, semantics_hash)
            baseline_count = len(baseline.findings)
            findings = worsened(inventory, baseline)
        except (ContractDocumentError, ValueError):
            print(json.dumps({"error": "invalid_baseline"}, sort_keys=True))
            return 2
    print(
        json.dumps(
            {
                "findings": [item.payload() for item in findings],
                "inventory": [item.payload() for item in inventory],
                "rules_sha256": rules_hash,
                "boundaries_sha256": boundaries_hash,
                "semantics_sha256": semantics_hash,
                "current_count": len(inventory),
                "baseline_count": baseline_count,
            },
            sort_keys=True,
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
