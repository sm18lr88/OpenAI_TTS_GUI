from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QT_VERSION_STR

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_QT_VERSION = QT_VERSION_STR
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
STABLE_OBJECT_NAMES = {
    "textEdit",
    "controlsSplitter",
    "voiceSettingsGroup",
    "modelCombo",
    "voiceCombo",
    "speedInput",
    "formatCombo",
    "instructionsGroup",
    "managePresetsButton",
    "instructionsEdit",
    "outputRunGroup",
    "pathEntry",
    "selectPathButton",
    "progressBar",
    "primaryButton",
    "cancelButton",
    "copyRequestIdsButton",
    "parallelismStatusLabel",
    "aboutText",
    "openLogButton",
    "aboutBackButton",
}
DISABLED_OBJECT_NAMES = {
    "managePresetsButton",
    "instructionsEdit",
    "cancelButton",
    "copyRequestIdsButton",
}


def _gui_smoke_environment(scale_factor: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["QT_SCALE_FACTOR"] = scale_factor
    return environment


def _run_gui_smoke(
    screenshot_path: Path, scale_factor: str = "1.0"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/pyinstaller_entry.py",
            "--gui-smoke",
            str(screenshot_path),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=_gui_smoke_environment(scale_factor),
        timeout=20,
    )


def test_gui_smoke_replaces_stale_capture_with_png_when_output_path_is_provided(
    tmp_path: Path,
) -> None:
    # Given: a stale non-PNG capture at the requested output path.
    screenshot_path = tmp_path / "gui-smoke.png"
    screenshot_path.write_text("stale capture", encoding="utf-8")

    # When: the packaged entry smoke surface receives that output path.
    result = _run_gui_smoke(screenshot_path)

    # Then: the existing success marker remains, and a fresh PNG replaces the stale file.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "gui-smoke=ok"
    assert screenshot_path.read_bytes().startswith(PNG_SIGNATURE)


def test_gui_smoke_returns_nonzero_when_screenshot_path_is_a_directory(tmp_path: Path) -> None:
    # Given: an existing directory instead of a writable PNG target.
    result = _run_gui_smoke(tmp_path)

    # When: the GUI smoke attempts to save the requested capture.

    # Then: it does not claim success for the missing screenshot artifact.
    assert result.returncode != 0
    assert result.stdout == ""


def test_gui_baseline_replaces_stale_json_and_screenshot_outputs(tmp_path: Path) -> None:
    # Given: stale non-baseline files at both requested output paths.
    json_path = tmp_path / "baseline.json"
    screenshot_path = tmp_path / "baseline.png"
    json_path.write_text("stale", encoding="utf-8")
    screenshot_path.write_text("stale", encoding="utf-8")

    # When: the isolated baseline runner captures a fresh GUI result.
    result = subprocess.run(
        [sys.executable, "tests/gui_baseline_support.py", str(json_path), str(screenshot_path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=_gui_smoke_environment("1.0"),
        timeout=20,
    )

    # Then: both stale files are replaced with parseable current evidence.
    assert result.returncode == 0, result.stderr
    assert screenshot_path.read_bytes().startswith(PNG_SIGNATURE)
    assert json.loads(json_path.read_text(encoding="utf-8"))["scale_factor"] == "1.0"


def test_gui_baseline_exits_normally_after_teardown(tmp_path: Path) -> None:
    # Given: a child process whose atexit handler proves normal interpreter shutdown.
    marker_path = tmp_path / "normal-exit.marker"
    json_path = tmp_path / "baseline.json"
    screenshot_path = tmp_path / "baseline.png"
    support_path = ROOT / "tests" / "gui_baseline_support.py"
    child_code = (
        "import atexit, runpy, sys; from pathlib import Path; "
        f"sys.path.insert(0, {str(support_path.parent)!r}); "
        f"marker = Path({str(marker_path)!r}); "
        "atexit.register(lambda: marker.write_text('normal', encoding='utf-8')); "
        f"sys.argv = [{str(support_path)!r}, {str(json_path)!r}, {str(screenshot_path)!r}]; "
        f"runpy.run_path({str(support_path)!r}, run_name='__main__')"
    )

    # When: the baseline runner writes evidence and terminates its QApplication.
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=_gui_smoke_environment("1.0"),
        timeout=20,
    )

    # Then: the process exits normally after it writes valid baseline evidence.
    assert result.returncode == 0, result.stderr
    assert marker_path.read_text(encoding="utf-8") == "normal"
    evidence = json.loads(json_path.read_text(encoding="utf-8"))
    assert evidence["scale_factor"] == "1.0"
    assert evidence["teardown"]["remaining_top_level_widgets"] == []
    assert evidence["teardown"]["application_released"]
    assert all(not state["running"] for state in evidence["teardown"]["thread_states"])


@pytest.mark.parametrize("scale_factor", ("2.0", "1.0", "1.5"))
def test_gui_baseline_records_stable_geometry_focus_and_state_at_each_scale(
    tmp_path: Path, scale_factor: str
) -> None:
    # Given: independent evidence paths for a fresh Qt process at one scale.
    json_path = tmp_path / f"baseline-{scale_factor}.json"
    screenshot_path = tmp_path / f"baseline-{scale_factor}.png"

    # When: the QTest baseline captures the shown main window.
    result = subprocess.run(
        [sys.executable, "tests/gui_baseline_support.py", str(json_path), str(screenshot_path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=_gui_smoke_environment(scale_factor),
        timeout=20,
    )

    # Then: required controls, focus traversal, state, and clipping results are stable.
    assert result.returncode == 0, result.stderr
    assert screenshot_path.read_bytes().startswith(PNG_SIGNATURE)
    evidence = json.loads(json_path.read_text(encoding="utf-8"))
    widgets = {widget["object_name"]: widget for widget in evidence["widgets"]}
    undersized = {
        name
        for name, widget in widgets.items()
        if widget["actual_bounds"][2] < widget["required_minimum_bounds"][0]
        or widget["actual_bounds"][3] < widget["required_minimum_bounds"][1]
    }
    expected_enabled = {name: name not in DISABLED_OBJECT_NAMES for name in STABLE_OBJECT_NAMES}
    actual_enabled = {name: widget["enabled"] for name, widget in widgets.items()}
    assert evidence["focus"] == {
        "tab_changes_focus": False,
        "keyboard_initial_owner": "textEdit",
        "keyboard_tab_owner": "textEdit",
        "keyboard_shift_tab_owner": "textEdit",
        "focus_chain_next_named_owner": "modelCombo",
        "focus_chain_previous_named_owner": "primaryButton",
    }
    assert evidence["scale_factor"] == scale_factor
    assert evidence["screenshot_size"][0] > 0
    assert evidence["screenshot_size"][1] > 0
    assert set(widgets) == STABLE_OBJECT_NAMES
    assert evidence["unaccounted_clipping"] == []
    assert evidence["teardown"]["remaining_top_level_widgets"] == []
    assert evidence["teardown"]["application_released"]
    assert all(not state["running"] for state in evidence["teardown"]["thread_states"])
    assert evidence["status_message"]["text"] == "Ready"
    assert evidence["status_message"]["text_bounds"][3] > 0
    assert isinstance(evidence["status_message"]["vertical_overflow"], bool)
    assert undersized == set(evidence["pre_existing_clipping"]) & STABLE_OBJECT_NAMES
    assert actual_enabled == expected_enabled
    assert all(widget["actual_bounds"][2] > 0 for widget in widgets.values())
    assert all(widget["within_parent_bounds"] for widget in widgets.values())


def test_geometry_baseline_reports_an_injected_undersized_control(tmp_path: Path) -> None:
    # Given: dedicated JSON and screenshot evidence paths.
    json_path = tmp_path / "baseline.json"
    screenshot_path = tmp_path / "baseline.png"

    # When: the baseline runner deliberately constrains the primary action.
    result = subprocess.run(
        [
            sys.executable,
            "tests/gui_baseline_support.py",
            str(json_path),
            str(screenshot_path),
            "--inject-primary-undersize",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=_gui_smoke_environment("1.0"),
        timeout=20,
    )

    # Then: the structured baseline reports the injected clipping defect by object name.
    assert result.returncode == 0, result.stderr
    evidence = json.loads(json_path.read_text(encoding="utf-8"))
    primary_button = next(
        widget for widget in evidence["widgets"] if widget["object_name"] == "primaryButton"
    )
    assert primary_button["actual_bounds"][2] < primary_button["required_minimum_bounds"][0]
    assert evidence["unaccounted_clipping"] == ["primaryButton"]
