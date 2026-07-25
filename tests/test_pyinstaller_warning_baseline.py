from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "classify_pyinstaller_warnings.py"


@dataclass(frozen=True, slots=True)
class WarningFixture:
    source_root: Path
    terminal_log: Path
    warn_file: Path


def _fixture(tmp_path: Path) -> WarningFixture:
    source_root = tmp_path / "source"
    scripts = source_root / "scripts"
    pyinstaller = source_root / "packaging" / "pyinstaller"
    scripts.mkdir(parents=True)
    pyinstaller.mkdir(parents=True)
    (source_root / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
    (pyinstaller / "openai_tts.spec").write_text("fixture\n", encoding="utf-8")
    (scripts / "pyinstaller_entry.py").write_text("fixture\n", encoding="utf-8")
    terminal_log = tmp_path / "pyinstaller.log"
    terminal_log.write_text(
        "UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or "
        "greater.\n"
        "UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or "
        "greater.\n"
        'WARNING: Hidden import "tzdata" not found!\n',
        encoding="utf-8",
    )
    warn_file = tmp_path / "warn-openai_tts.txt"
    warn_file.write_text(
        "missing module named openai_tts_gui.tts.TTSService - imported by openai_tts_gui.tts\n",
        encoding="utf-8",
    )
    return WarningFixture(source_root, terminal_log, warn_file)


def _run(
    fixture: WarningFixture,
    report: Path,
    policy: Path,
    write_policy: bool,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        str(SCRIPT),
        "--terminal-log",
        str(fixture.terminal_log),
        "--warn-file",
        str(fixture.warn_file),
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


def _freeze(fixture: WarningFixture, policy: Path) -> None:
    result = _run(fixture, policy.with_suffix(".report.json"), policy, write_policy=True)
    assert result.returncode == 0, result.stderr


def test_pyinstaller_warning_baseline_classifies_terminal_and_warn_records(tmp_path: Path) -> None:
    # Given: terminal warnings and a real-format PyInstaller missing-module record.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "warning-policy.json"
    _freeze(fixture, policy)

    # When: classification reads both build evidence streams.
    result = _run(fixture, tmp_path / "warnings.json", policy, write_policy=False)

    # Then: every expected record, including the TTSService missing module, is retained.
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "warnings.json").read_text(encoding="utf-8"))
    assert report["missing_module_records"] == [
        "missing module named openai_tts_gui.tts.TTSService - imported by openai_tts_gui.tts"
    ]
    assert report["status"] == "ok"


def test_warning_baseline_accepts_reordered_importers(tmp_path: Path) -> None:
    # Given: a policy frozen from one ordering and aggregation of importer semantics.
    fixture = _fixture(tmp_path)
    fixture.warn_file.write_text(
        "missing module named optional_module - imported by importer_b (optional), importer_a "
        "(top-level)\n",
        encoding="utf-8",
    )
    policy = tmp_path / "warning-policy.json"
    _freeze(fixture, policy)
    fixture.warn_file.write_text(
        "missing module named optional_module - imported by importer_a (top-level)\n"
        "missing module named optional_module - imported by importer_b (optional)\n",
        encoding="utf-8",
    )

    # When: the same importer set is emitted in a different order and line aggregation.
    result = _run(fixture, tmp_path / "warnings.json", policy, write_policy=False)

    # Then: canonical module/importer semantics validate.
    assert result.returncode == 0, result.stderr


def test_pyinstaller_warning_baseline_rejects_changed_importer_semantics(tmp_path: Path) -> None:
    # Given: an established canonical warning baseline.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "warning-policy.json"
    _freeze(fixture, policy)
    fixture.warn_file.write_text(
        "missing module named openai_tts_gui.tts.TTSService - imported by changed_importer\n",
        encoding="utf-8",
    )

    # When: a warning reports a different importer semantic set.
    result = _run(fixture, tmp_path / "warnings.json", policy, write_policy=False)

    # Then: the unknown and missing semantic records fail closed.
    assert result.returncode == 1
    assert "changed_importer" in result.stdout


def test_pyinstaller_warning_baseline_rejects_unknown_and_empty_logs(tmp_path: Path) -> None:
    # Given: an established policy followed by an unrecognized warning record.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "warning-policy.json"
    _freeze(fixture, policy)
    fixture.warn_file.write_text(
        "missing module named surprise - imported by openai_tts_gui.tts\n",
        encoding="utf-8",
    )

    # When: the unknown record is classified.
    unknown = _run(fixture, tmp_path / "unknown.json", policy, write_policy=False)

    # Then: it fails closed; empty evidence also fails required-category checks.
    assert unknown.returncode == 1
    assert "surprise" in unknown.stdout
    fixture.terminal_log.write_text("", encoding="utf-8")
    fixture.warn_file.write_text("", encoding="utf-8")
    empty = _run(fixture, tmp_path / "empty.json", policy, write_policy=False)
    assert empty.returncode == 1
    assert "missing expected category" in empty.stdout


def test_pyinstaller_warning_baseline_rejects_invalid_version_and_stale_evidence(
    tmp_path: Path,
) -> None:
    # Given: a generated warning policy and terminal evidence made stale afterward.
    fixture = _fixture(tmp_path)
    policy = tmp_path / "warning-policy.json"
    _freeze(fixture, policy)
    os.utime(fixture.terminal_log, (1, 1))

    # When: stale evidence and then a version-zero policy are classified.
    stale = _run(fixture, tmp_path / "stale.json", policy, write_policy=False)
    contents = json.loads(policy.read_text(encoding="utf-8"))
    contents["version"] = 0
    policy.write_text(json.dumps(contents), encoding="utf-8")
    schema = _run(fixture, tmp_path / "schema.json", policy, write_policy=False)

    # Then: both freshness and exact policy-schema checks fail.
    assert stale.returncode == 1
    assert "stale" in stale.stdout
    assert schema.returncode == 1
    assert "invalid policy" in schema.stdout
