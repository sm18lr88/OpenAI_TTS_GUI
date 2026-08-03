from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QT_VERSION_STR

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_QT_VERSION = QT_VERSION_STR
ENTRY_PATH = ROOT / "scripts" / "pyinstaller_entry.py"


def _observe_teardown(screenshot_path: Path, marker_path: Path) -> dict[str, bool | int]:
    source_path = repr(str(ROOT / "src"))
    entry_path = repr(str(ENTRY_PATH))
    output_path = repr(str(screenshot_path))
    marker = repr(str(marker_path))
    child_code = (
        "import atexit, json, runpy, sys; from pathlib import Path; "
        f"sys.path.insert(0, {source_path}); "
        "from PyQt6.QtWidgets import QApplication\n"
        "from openai_tts_gui import gui\n"
        "original_window_type = gui.TTSWindow\n"
        "class ObservedWindow(original_window_type):\n"
        "    deferred_delete_called = False\n"
        "    def deleteLater(self):\n"
        "        type(self).deferred_delete_called = True\n"
        "        super().deleteLater()\n"
        "gui.TTSWindow = ObservedWindow\n"
        f"marker = Path({marker})\n"
        "atexit.register(lambda: marker.write_text('normal', encoding='utf-8'))\n"
        f"entry = runpy.run_path({entry_path})\n"
        f"result = entry['_gui_smoke']({output_path})\n"
        "deferred_delete_called = ObservedWindow.deferred_delete_called\n"
        "receipt = {'result': result, 'deferred_delete_called': deferred_delete_called}\n"
        "receipt['application_released'] = QApplication.instance() is None\n"
        "print(json.dumps(receipt))"
    )
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=environment,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


def test_gui_smoke_deletes_window_and_releases_application_after_success(tmp_path: Path) -> None:
    # Given: a writable image target and a child-side observed smoke window.
    screenshot_path = tmp_path / "smoke.png"
    marker_path = tmp_path / "success.marker"

    # When: the packaged smoke route completes normally.
    receipt = _observe_teardown(screenshot_path, marker_path)

    # Then: it delays window deletion, releases QApplication, and exits normally.
    assert receipt == {"result": 0, "deferred_delete_called": True, "application_released": True}
    assert marker_path.read_text(encoding="utf-8") == "normal"


def test_gui_smoke_deletes_window_and_releases_application_after_save_failure(
    tmp_path: Path,
) -> None:
    # Given: a directory image target that makes the screenshot save fail.
    marker_path = tmp_path / "failure.marker"

    # When: the packaged smoke route attempts that invalid save.
    receipt = _observe_teardown(tmp_path, marker_path)

    # Then: the error route performs the same explicit Qt cleanup and exits normally.
    assert receipt == {"result": 1, "deferred_delete_called": True, "application_released": True}
    assert marker_path.read_text(encoding="utf-8") == "normal"
