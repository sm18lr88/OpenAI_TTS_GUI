from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_distribution_inventory.py"


@dataclass(frozen=True, slots=True)
class ArtifactFixture:
    source_root: Path
    wheel: Path
    sdist: Path
    frozen_root: Path


def _write_wheel(path: Path, members: tuple[str, ...]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, "baseline")


def _write_sdist(path: Path, members: tuple[str, ...]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for member in members:
            content = b"baseline"
            entry = tarfile.TarInfo(member)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))


def _fixture(tmp_path: Path) -> ArtifactFixture:
    source_root = tmp_path / "source"
    scripts = source_root / "scripts"
    pyinstaller = source_root / "packaging" / "pyinstaller"
    scripts.mkdir(parents=True)
    pyinstaller.mkdir(parents=True)
    (source_root / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
    (pyinstaller / "openai_tts.spec").write_text("fixture\n", encoding="utf-8")
    (scripts / "pyinstaller_entry.py").write_text("fixture\n", encoding="utf-8")
    wheel = tmp_path / "package.whl"
    sdist = tmp_path / "package.tar.gz"
    frozen_root = tmp_path / "OpenAI-TTS"
    frozen_root.mkdir()
    (frozen_root / "openai_tts_bin.exe").write_bytes(b"MZbinary")
    _write_wheel(wheel, ("openai_tts_gui/main.py", "openai_tts_gui/utils.py"))
    _write_sdist(
        sdist,
        (
            "package-1.0/src/openai_tts_gui/utils.py",
            "package-1.0/tests/test_smoke.py",
        ),
    )
    return ArtifactFixture(source_root, wheel, sdist, frozen_root)


def _run(
    fixture: ArtifactFixture,
    report: Path,
    policy: Path,
    write_policy: bool,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(SCRIPT),
        "--wheel",
        str(fixture.wheel),
        "--sdist",
        str(fixture.sdist),
        "--frozen-root",
        str(fixture.frozen_root),
        "--source-root",
        str(fixture.source_root),
        "--report",
        str(report),
    ]
    if write_policy:
        arguments.extend(("--write-policy", str(policy)))
    else:
        arguments.extend(("--policy", str(policy)))
    return subprocess.run(arguments, check=False, capture_output=True, encoding="utf-8")


def _freeze(fixture: ArtifactFixture, policy: Path) -> None:
    result = _run(fixture, policy.with_suffix(".report.json"), policy, write_policy=True)
    assert result.returncode == 0, result.stderr


def test_distribution_inventory_accepts_exact_fresh_artifacts(tmp_path: Path) -> None:
    # Given: fresh wheel, sdist, frozen-runtime, and source fixtures.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "inventory-policy.json"
    _freeze(fixture, policy)

    # When: verification reads the generated exact inventory baseline.
    result = _run(fixture, tmp_path / "inventory.json", policy, write_policy=False)

    # Then: the matching artifact set is accepted.
    assert result.returncode == 0, result.stderr
    assert json.loads(policy.read_text(encoding="utf-8"))["version"] == 3


def test_distribution_inventory_accepts_nondeterministic_executable_bytes(tmp_path: Path) -> None:
    # Given: a frozen policy for a structurally valid executable.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "inventory-policy.json"
    _freeze(fixture, policy)
    (fixture.frozen_root / "openai_tts_bin.exe").write_bytes(b"MZrebuilt-binary")

    # When: a clean rebuild changes only the generated executable bytes.
    result = _run(fixture, tmp_path / "inventory.json", policy, write_policy=False)

    # Then: its required nonempty PE-format invariant preserves reproducibility.
    assert result.returncode == 0, result.stderr


def test_distribution_inventory_rejects_invalid_nondeterministic_executable_format(
    tmp_path: Path,
) -> None:
    # Given: a frozen policy for a structurally valid executable.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "inventory-policy.json"
    _freeze(fixture, policy)
    (fixture.frozen_root / "openai_tts_bin.exe").write_bytes(b"not-a-pe")

    # When: the generated member no longer has its required format.
    result = _run(fixture, tmp_path / "inventory.json", policy, write_policy=False)

    # Then: semantic validation fails without weakening exact membership.
    assert result.returncode == 1
    assert "PE" in result.stdout


@pytest.mark.parametrize(
    "forbidden_member",
    [
        ".env",
        "runtime/credentials.json",
        "user-data/secret.txt",
        ".omo/evidence/build.log",
    ],
)
def test_distribution_inventory_rejects_unapproved_payloads(
    tmp_path: Path,
    forbidden_member: str,
) -> None:
    # Given: an exact-policy baseline for clean artifacts.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "inventory-policy.json"
    _freeze(fixture, policy)
    _write_wheel(fixture.wheel, ("openai_tts_gui/utils.py", forbidden_member))

    # When: a wheel contains an arbitrary payload outside the approved inventory.
    result = _run(fixture, tmp_path / "inventory.json", policy, write_policy=False)

    # Then: verification fails closed and names that payload.
    assert result.returncode == 1
    assert forbidden_member in result.stdout


def test_distribution_inventory_rejects_stale_artifact_and_invalid_policy_version(
    tmp_path: Path,
) -> None:
    # Given: a frozen policy, then a wheel made older than its build baseline.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "inventory-policy.json"
    _freeze(fixture, policy)
    contents = json.loads(policy.read_text(encoding="utf-8"))
    os.utime(fixture.wheel, (1, 1))

    # When: the stale wheel is verified.
    stale_result = _run(fixture, tmp_path / "stale.json", policy, write_policy=False)

    # Then: freshness fails independently of policy schema validation.
    assert stale_result.returncode == 1
    assert "stale" in stale_result.stdout
    contents["version"] = 0
    policy.write_text(json.dumps(contents), encoding="utf-8")
    schema_result = _run(fixture, tmp_path / "schema.json", policy, write_policy=False)
    assert schema_result.returncode == 1
    assert "invalid policy" in schema_result.stdout


@pytest.mark.parametrize("mutation", ["added", "missing"])
def test_distribution_inventory_rejects_frozen_runtime_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    # Given: a complete frozen-runtime baseline.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "inventory-policy.json"
    _freeze(fixture, policy)
    target = fixture.frozen_root / "openai_tts_bin.exe"
    if mutation == "added":
        target = fixture.frozen_root / "runtime" / "unexpected.dll"
        target.parent.mkdir()
        target.write_bytes(b"unexpected")
    else:
        target.unlink()

    # When: one frozen file is added or removed after policy capture.
    result = _run(fixture, tmp_path / "inventory.json", policy, write_policy=False)

    # Then: the exact frozen baseline rejects the drift.
    assert result.returncode == 1
    assert target.name in result.stdout
