from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_release_versions_stay_in_sync() -> None:
    pyproject = tomllib.loads(_read("pyproject.toml"))
    expected = pyproject["project"]["version"]
    settings_source = _read("src/openai_tts_gui/config/settings.py")
    package_source = _read("src/openai_tts_gui/__init__.py")
    installer_source = _read("packaging/windows/installer.nsi")
    release_workflow = _read(".github/workflows/release.yml")

    assert f'DEFAULT_APP_VERSION: Final[str] = "{expected}"' in settings_source
    assert f'DEFAULT_APP_VERSION = "{expected}"' in package_source
    assert f'!define APP_VERSION "{expected}"' in installer_source
    assert f"OpenAI TTS v{expected}" not in release_workflow
    assert "OpenAI TTS ${{ github.ref_name }}" in release_workflow


def test_release_workflow_runs_quality_gates_and_generates_checksums() -> None:
    release_workflow = _read(".github/workflows/release.yml")

    assert "uv run ruff check" in release_workflow
    assert "uv run ty check" in release_workflow
    assert "uv run pytest" in release_workflow
    assert "--self-check" in release_workflow
    assert "SHA256SUMS" in release_workflow
    assert "Get-FileHash" in release_workflow or "sha256sum" in release_workflow


def test_ci_and_release_enforce_independent_coverage_thresholds() -> None:
    # Given: the repository coverage policy and both hosted quality-gate workflows.
    pyproject = tomllib.loads(_read("pyproject.toml"))
    workflows = [_read(".github/workflows/ci.yml"), _read(".github/workflows/release.yml")]
    coverage_command = (
        "uv run pytest --ignore=tests/perf --cov=openai_tts_gui --cov-branch "
        "--cov-report=term-missing --cov-report=json:coverage.json"
    )
    threshold_command = (
        "uv run scripts/check_coverage_thresholds.py coverage.json "
        "--min-statements 90 --min-branches 90"
    )

    # When: machine-consumed coverage configuration is inspected.
    combined_floor = pyproject["tool"]["coverage"]["report"]["fail_under"]

    # Then: every hosted gate uses the same measured report and strict independent floors.
    assert combined_floor == 97
    assert all(coverage_command in workflow for workflow in workflows)
    assert all(threshold_command in workflow for workflow in workflows)


def test_pyinstaller_entry_supports_artifact_self_check() -> None:
    entry_source = _read("scripts/pyinstaller_entry.py")

    assert "--self-check" in entry_source
    assert "--gui-smoke" in entry_source
    assert "gui-smoke=ok" in entry_source
    assert "env_snapshot" in entry_source
    assert "openai_tts_gui.main import main" in entry_source


def test_installer_uses_per_user_install_and_safe_uninstall_guard() -> None:
    installer_source = _read("packaging/windows/installer.nsi")

    assert "RequestExecutionLevel user" in installer_source
    assert 'InstallDir "$LOCALAPPDATA\\Programs\\OpenAI-TTS"' in installer_source
    assert "InstallDirRegKey HKCU" in installer_source
    assert "WriteRegStr HKCU" in installer_source
    assert "HKLM" not in installer_source
    assert '!insertmacro MUI_PAGE_LICENSE "..\\..\\LICENSE"' in installer_source
    assert 'CreateShortcut "$DESKTOP\\OpenAI TTS.lnk"' not in installer_source
    assert re.search(r'ReadRegStr \$0 HKCU "Software\\OpenAI-TTS" "InstallDir"', installer_source)
    assert 'StrCmp $0 "$INSTDIR" 0 un.safe_abort' in installer_source
    assert 'IfFileExists "$INSTDIR\\openai_tts_bin.exe" 0 un.safe_abort' in installer_source
    assert 'IfFileExists "$INSTDIR\\.openai-tts-install" 0 un.safe_abort' in installer_source
    assert 'IfFileExists "$INSTDIR\\*.*" 0 install.continue' in installer_source
    assert 'RMDir /r "$INSTDIR"' not in installer_source
    assert "un.safe_abort:" in installer_source


def test_readme_documents_support_privacy_trust_and_certification_limits() -> None:
    readme = _read("README.md")

    assert "Show appreciation" in readme
    assert "https://paypal.me/LeoRiera" in readme
    assert "Privacy and trust" in readme
    assert "OpenAI" in readme and "text" in readme
    assert "Windows App Certification Kit" in readme
    assert "does not claim certification" in readme
