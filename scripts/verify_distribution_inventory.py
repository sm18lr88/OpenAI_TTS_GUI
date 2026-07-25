from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path

POLICY_VERSION = 3
SOURCE_FILES = (
    "pyproject.toml",
    "packaging/pyinstaller/openai_tts.spec",
    "scripts/pyinstaller_entry.py",
)
NONDETERMINISTIC_FROZEN_MEMBERS = {
    "_internal/base_library.zip": "semantic:zip",
    "openai_tts_bin.exe": "semantic:pe",
}


class PolicyError(Exception):
    pass


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze and verify exact distribution inventories."
    )
    policy = parser.add_mutually_exclusive_group(required=True)
    policy.add_argument("--policy", type=Path)
    policy.add_argument("--write-policy", type=Path)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def _sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _source_identity(source_root: Path) -> dict[str, str]:
    missing = [relative for relative in SOURCE_FILES if not (source_root / relative).is_file()]
    if missing:
        raise PolicyError(f"source identity files missing: {', '.join(missing)}")
    return {relative: _sha256_file(source_root / relative) for relative in SOURCE_FILES}


def _wheel_members(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            member.filename.replace("\\", "/"): _sha256_bytes(archive.read(member))
            for member in archive.infolist()
            if not member.is_dir()
        }


def _sdist_members(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:gz") as archive:
        members: dict[str, str] = {}
        for member in archive.getmembers():
            contents = archive.extractfile(member)
            if member.isfile() and contents is not None:
                members[member.name.replace("\\", "/").partition("/")[2]] = _sha256_bytes(
                    contents.read()
                )
        return members


def _frozen_members(path: Path) -> dict[str, str]:
    return {
        member.relative_to(path).as_posix(): _sha256_file(member)
        for member in path.rglob("*")
        if member.is_file()
    }


def _manifests(arguments: argparse.Namespace) -> dict[str, dict[str, str]]:
    return {
        "frozen": _frozen_members(arguments.frozen_root),
        "sdist": _sdist_members(arguments.sdist),
        "wheel": _wheel_members(arguments.wheel),
    }


def _not_before(arguments: argparse.Namespace) -> int:
    return int(
        min(
            arguments.wheel.stat().st_mtime,
            arguments.sdist.stat().st_mtime,
            arguments.frozen_root.stat().st_mtime,
        )
    )


def _freeze_policy(arguments: argparse.Namespace, manifests: dict[str, dict[str, str]]) -> None:
    frozen = manifests["frozen"]
    for member, invariant in NONDETERMINISTIC_FROZEN_MEMBERS.items():
        if member in frozen:
            frozen[member] = invariant
    semantic_errors = _semantic_frozen_errors(arguments.frozen_root, frozen)
    if semantic_errors:
        raise PolicyError("; ".join(semantic_errors))
    policy = {
        "artifacts": manifests,
        "not_before_unix_seconds": _not_before(arguments),
        "source_identity": _source_identity(arguments.source_root),
        "version": POLICY_VERSION,
    }
    arguments.write_policy.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_policy(path: Path) -> tuple[int, dict[str, str], dict[str, dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required_keys = {"artifacts", "not_before_unix_seconds", "source_identity", "version"}
    if not isinstance(payload, dict) or set(payload) != required_keys:
        raise PolicyError("invalid policy schema")
    if payload["version"] != POLICY_VERSION:
        raise PolicyError("invalid policy version")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != {"frozen", "sdist", "wheel"}:
        raise PolicyError("invalid policy artifacts")
    not_before = payload["not_before_unix_seconds"]
    source_identity = payload["source_identity"]
    if not isinstance(not_before, int):
        raise PolicyError("invalid policy freshness")
    if not isinstance(source_identity, dict) or set(source_identity) != set(SOURCE_FILES):
        raise PolicyError("invalid policy source identity")
    source_values_are_strings = all(
        isinstance(name, str) and isinstance(value, str) for name, value in source_identity.items()
    )
    if not source_values_are_strings:
        raise PolicyError("invalid policy source identity")
    typed_artifacts: dict[str, dict[str, str]] = {}
    for artifact_name, members in artifacts.items():
        if not isinstance(artifact_name, str) or not isinstance(members, dict):
            raise PolicyError("invalid policy artifacts")
        member_values_are_strings = all(
            isinstance(name, str) and isinstance(value, str) for name, value in members.items()
        )
        if not member_values_are_strings:
            raise PolicyError("invalid policy artifacts")
        typed_artifacts[artifact_name] = members
    return not_before, source_identity, typed_artifacts


def _freshness_errors(arguments: argparse.Namespace, not_before: int) -> list[str]:
    paths = (arguments.wheel, arguments.sdist, arguments.frozen_root)
    return [f"stale artifact: {path}" for path in paths if int(path.stat().st_mtime) < not_before]


def _manifest_errors(
    expected: dict[str, dict[str, str]], actual: dict[str, dict[str, str]]
) -> list[str]:
    errors: list[str] = []
    for name in ("wheel", "sdist", "frozen"):
        expected_members = expected[name]
        actual_members = actual[name]
        errors.extend(
            f"{name} missing approved member: {member}"
            for member in sorted(set(expected_members) - set(actual_members))
        )
        errors.extend(
            f"{name} includes unapproved member: {member}"
            for member in sorted(set(actual_members) - set(expected_members))
        )
        errors.extend(
            f"{name} changed approved member: {member}"
            for member in sorted(set(expected_members).intersection(actual_members))
            if not expected_members[member].startswith("semantic:")
            and expected_members[member] != actual_members[member]
        )
    return errors


def _semantic_frozen_errors(root: Path, members: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for member, invariant in members.items():
        if not invariant.startswith("semantic:"):
            continue
        path = root / member
        if not path.is_file():
            errors.append(f"frozen semantic member is missing: {member}")
            continue
        contents = path.read_bytes()
        if not contents:
            errors.append(f"frozen semantic member is empty: {member}")
        elif invariant == "semantic:pe" and not contents.startswith(b"MZ"):
            errors.append(f"frozen semantic member is not PE format: {member}")
        elif invariant == "semantic:zip" and not zipfile.is_zipfile(path):
            errors.append(f"frozen semantic member is not ZIP format: {member}")
    return errors


def _test_policy_errors(manifests: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if any(member.startswith("tests/") for member in manifests["wheel"]):
        errors.append("wheel must exclude tests")
    if not any(member.startswith("tests/") for member in manifests["sdist"]):
        errors.append("sdist must include tests")
    for name in ("wheel", "sdist"):
        if "openai_tts_gui/utils.py" not in manifests[name] and (
            "src/openai_tts_gui/utils.py" not in manifests[name]
        ):
            errors.append(f"{name} must retain utils.py")
    return errors


def main() -> int:
    arguments = _parse_arguments()
    manifests = _manifests(arguments)
    if arguments.write_policy is not None:
        _freeze_policy(arguments, manifests)
        report = {"artifacts": manifests, "status": "frozen"}
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))
        return 0
    try:
        not_before, source_identity, expected_artifacts = _load_policy(arguments.policy)
    except (OSError, PolicyError, json.JSONDecodeError) as error:
        report = {"errors": [f"invalid policy: {error}"], "status": "failed"}
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))
        return 1
    errors = _freshness_errors(arguments, not_before)
    if source_identity != _source_identity(arguments.source_root):
        errors.append("source identity differs from policy")
    errors.extend(_manifest_errors(expected_artifacts, manifests))
    errors.extend(_semantic_frozen_errors(arguments.frozen_root, expected_artifacts["frozen"]))
    errors.extend(_test_policy_errors(manifests))
    report = {
        "artifacts": manifests,
        "errors": errors,
        "status": "ok" if not errors else "failed",
    }
    arguments.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
