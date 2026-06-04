from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _assert_exists(path: str) -> Path:
    file_path = ROOT / path
    assert file_path.exists(), f"Missing expected file: {path}"
    return file_path


def _write_report(tmp_path: Path, name: str, content: str) -> Path:
    report_path = tmp_path / name
    report_path.write_text(content, encoding="utf-8")
    return report_path


def test_msix_manifest_template_has_required_placeholders_and_assets() -> None:
    manifest = _assert_exists("packaging/msix/AppxManifest.xml.in").read_text(encoding="utf-8")

    assert "openai_tts_bin.exe" in manifest
    assert "runFullTrust" in manifest
    assert 'ProcessorArchitecture="x64"' in manifest
    assert "{{VERSION}}" in manifest or "${VERSION}" in manifest
    assert "{{PUBLISHER}}" in manifest or "${PUBLISHER}" in manifest
    assert "Square44x44Logo" in manifest
    assert "Square150x150Logo" in manifest
    assert "Wide310x150Logo" in manifest
    assert "StoreLogo" in manifest or "Logo" in manifest


def test_pyinstaller_exe_manifest_declares_dpi_awareness() -> None:
    spec = _read("openai_tts.spec")
    manifest = _assert_exists("packaging/windows/openai_tts_bin.exe.manifest").read_text(
        encoding="utf-8"
    )

    assert "openai_tts_bin.exe.manifest" in spec
    assert "asInvoker" in manifest
    assert "PerMonitorV2" in manifest


def test_build_msix_local_script_stages_signs_and_avoids_nsis() -> None:
    script = _assert_exists("scripts/build_msix_local.ps1").read_text(encoding="utf-8")

    assert "dist\\OpenAI-TTS" in script
    assert "makeappx" in script.lower()
    assert "dist\\OpenAI-TTS.msix" in script
    assert "signtool" in script.lower()
    assert "thumbprint" in script.lower() or "/sha1" in script.lower()
    assert ".pfx" in script.lower() or "/f" in script.lower()
    assert "NSIS" not in script
    assert "_internal\\VCRUNTIME140.dll" in script
    assert "_internal\\VCRUNTIME140_1.dll" in script
    assert "_internal\\PyQt6\\Qt6\\bin\\Qt6Pdf.dll" in script
    assert "_internal\\PyQt6\\Qt6\\bin\\opengl32sw.dll" in script


def test_validate_wack_local_script_invokes_appcert_and_checks_report() -> None:
    script = _assert_exists("scripts/validate_wack_local.ps1").read_text(encoding="utf-8")

    assert "appcert.exe" in script.lower()
    assert "reports\\wack" in script.lower()
    assert "scripts\\check_wack_report.py" in script.replace("/", "\\")
    assert "unavailable" in script.lower() or "not found" in script.lower()
    assert "exit 1" in script.lower() or "throw" in script.lower()


@pytest.mark.parametrize(
    ("name", "xml_text", "expected_exit_code"),
    [
        (
            "pass.xml",
            (
                "<PackageValidationResults>\n"
                "  <Summary>\n"
                "    <OverallResult>PASS</OverallResult>\n"
                "  </Summary>\n"
                "</PackageValidationResults>\n"
            ),
            0,
        ),
        (
            "fail.xml",
            (
                "<PackageValidationResults>\n"
                "  <Summary>\n"
                "    <OverallResult>FAIL</OverallResult>\n"
                "  </Summary>\n"
                "</PackageValidationResults>\n"
            ),
            1,
        ),
        (
            "unknown.xml",
            (
                "<PackageValidationResults>\n"
                "  <Summary>\n"
                "    <OverallResult>UNKNOWN</OverallResult>\n"
                "  </Summary>\n"
                "</PackageValidationResults>\n"
            ),
            1,
        ),
    ],
)
def test_check_wack_report_cli_accepts_only_explicit_pass_reports(
    tmp_path: Path,
    name: str,
    xml_text: str,
    expected_exit_code: int,
) -> None:
    script = _assert_exists("scripts/check_wack_report.py")
    report = _write_report(tmp_path, name, xml_text.strip() + "\n")

    result = subprocess.run(
        [sys.executable, str(script), str(report)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == expected_exit_code
    if expected_exit_code == 0:
        assert "pass" in (result.stdout + result.stderr).lower()


def test_check_wack_report_cli_rejects_real_wack_schema_with_failed_tests(
    tmp_path: Path,
) -> None:
    script = _assert_exists("scripts/check_wack_report.py")
    report = _write_report(
        tmp_path,
        "real-fail.xml",
        """
        <REPORT OVERALL_RESULT="WARNING">
          <REQUIREMENTS>
            <REQUIREMENT TITLE="Package sanity test">
              <TEST NAME="Blocked executables">
                <RESULT>FAIL</RESULT>
              </TEST>
            </REQUIREMENT>
          </REQUIREMENTS>
        </REPORT>
        """.strip()
        + "\n",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(report)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Blocked executables" in result.stdout


def test_check_wack_report_cli_accepts_real_wack_schema_with_all_passes(
    tmp_path: Path,
) -> None:
    script = _assert_exists("scripts/check_wack_report.py")
    report = _write_report(
        tmp_path,
        "real-pass.xml",
        """
        <REPORT OVERALL_RESULT="PASS">
          <REQUIREMENTS>
            <REQUIREMENT TITLE="Package sanity test">
              <TEST NAME="App manifest">
                <RESULT>PASS</RESULT>
              </TEST>
            </REQUIREMENT>
          </REQUIREMENTS>
        </REPORT>
        """.strip()
        + "\n",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(report)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_msix_docs_describe_optional_local_workflow_without_store_claims() -> None:
    msix_docs = _assert_exists("docs/MSIX_LOCAL.md").read_text(encoding="utf-8")
    release_checklist = _read("docs/RELEASE_CHECKLIST.md")

    combined = f"{msix_docs}\n{release_checklist}".lower()

    assert "optional" in combined and "local" in combined
    assert "msix" in combined
    assert "makeappx" in combined
    assert "signtool" in combined
    assert "app certification kit" in combined or "appcert" in combined
    assert "not claimed" in combined or "does not claim certification" in combined
    assert "real report" in combined or "actual" in combined
    assert "store" in combined
    assert "signed-file" in combined
    assert "blocked-executable" in combined


def test_release_workflow_keeps_nsis_primary_and_does_not_depend_on_msix_wack() -> None:
    release_workflow = _read(".github/workflows/release.yml")

    assert "OpenAI-TTS-Setup.exe" in release_workflow
    assert "makensis.exe" in release_workflow
    assert "makeappx" not in release_workflow.lower()
    assert "appcert" not in release_workflow.lower()
    assert "wack" not in release_workflow.lower()
