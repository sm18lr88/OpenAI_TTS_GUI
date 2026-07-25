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
SUPPORT_PATH = ROOT / "tests" / "gui_baseline_support.py"
ENTRY_PATH = ROOT / "scripts" / "pyinstaller_entry.py"


def _environment(seam: str = "") -> dict[str, str]:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "minimal" if seam == "active" else "offscreen"
    return environment


def _baseline_receipt(seam: str, tmp_path: Path) -> dict[str, bool | str]:
    image_path = tmp_path / f"{seam}.png"
    marker_path = tmp_path / f"{seam}.marker"
    child_code = (
        "import atexit, importlib.util, json, sys; from pathlib import Path\n"
        f"sys.path.insert(0, {str(SUPPORT_PATH.parent)!r})\n"
        "spec = importlib.util.spec_from_file_location(\n"
        f"    'lifecycle_support', {str(SUPPORT_PATH)!r}\n"
        ")\n"
        "support = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = support\n"
        "spec.loader.exec_module(support)\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "from PyQt6.QtCore import QThread\n"
        "original = support.TTSWindow\n"
        "class ObservedWindow(original):\n"
        "    instances = []\n"
        "    close_called = False\n"
        "    delete_later_called = False\n"
        "    thread_stopped_before_window_delete = True\n"
        "    def __init__(self):\n"
        "        super().__init__()\n"
        "        self.running_child = None\n"
        "        type(self).instances.append(self)\n"
        "    def close(self):\n"
        "        type(self).close_called = True\n"
        "        return super().close()\n"
        "    def deleteLater(self):\n"
        "        type(self).thread_stopped_before_window_delete = (\n"
        "            self.running_child is None or not self.running_child.isRunning()\n"
        "        )\n"
        "        type(self).delete_later_called = True\n"
        "        return super().deleteLater()\n"
        "support.TTSWindow = ObservedWindow\n"
        "def fail(*args, **kwargs):\n"
        "    raise support.GuiBaselineError('injected')\n"
        f"seam = {seam!r}\n"
        "if seam == 'missing': support._required_widget = fail\n"
        "if seam == 'focus': support.capture_focus_baseline = fail\n"
        "if seam == 'primary_cleanup':\n"
        "    support.capture_focus_baseline = fail\n"
        "    def cleanup_close(self):\n"
        "        type(self).close_called = True\n"
        "        original.close(self)\n"
        "        raise RuntimeError('cleanup injected')\n"
        "    ObservedWindow.close = cleanup_close\n"
        "if seam == 'running_child':\n"
        "    original_init = ObservedWindow.__init__\n"
        "    def running_init(self):\n"
        "        original_init(self)\n"
        "        self.running_child = QThread(self)\n"
        "        self.running_child.start()\n"
        "    ObservedWindow.__init__ = running_init\n"
        "    support._required_widget = fail\n"
        "if seam == 'active':\n"
        "    support.QTest = type('QTest', (), {\n"
        "        'qWaitForWindowActive': staticmethod(lambda *args: False)\n"
        "    })\n"
        "if seam == 'save':\n"
        "    class Pixmap:\n"
        "        def save(self, path): raise support.GuiBaselineError('injected')\n"
        "        def width(self): return 1\n"
        "        def height(self): return 1\n"
        "    ObservedWindow.grab = lambda self: Pixmap()\n"
        "atexit.register(\n"
        f"    lambda: Path({str(marker_path)!r}).write_text('normal', encoding='utf-8')\n"
        ")\n"
        "try:\n"
        f"    support.capture_gui_baseline(Path({str(image_path)!r}))\n"
        "except support.GuiBaselineError as error:\n"
        "    window = ObservedWindow.instances[-1]\n"
        "    print(json.dumps({\n"
        "        'error': type(error).__name__,\n"
        "        'closed': ObservedWindow.close_called,\n"
        "        'deleted': ObservedWindow.delete_later_called,\n"
        "        'application_released': QApplication.instance() is None,\n"
        "        'notes': getattr(error, '__notes__', []),\n"
        "        'thread_stopped_before_window_delete': getattr(\n"
        "            ObservedWindow, 'thread_stopped_before_window_delete', True\n"
        "        ),\n"
        "    }))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=ROOT,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=_environment(seam),
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert marker_path.read_text(encoding="utf-8") == "normal"
    return json.loads(result.stdout)


@pytest.mark.parametrize("seam", ("missing", "focus", "active", "save"))
def test_baseline_releases_qt_resources_after_unexpected_exception(
    seam: str, tmp_path: Path
) -> None:
    receipt = _baseline_receipt(seam, tmp_path)
    assert receipt == {
        "error": "GuiBaselineError",
        "closed": True,
        "deleted": True,
        "application_released": True,
        "notes": [],
        "thread_stopped_before_window_delete": True,
    }


def test_baseline_preserves_primary_error_when_cleanup_also_fails(tmp_path: Path) -> None:
    receipt = _baseline_receipt("primary_cleanup", tmp_path)
    assert receipt == {
        "error": "GuiBaselineError",
        "closed": True,
        "deleted": True,
        "application_released": True,
        "notes": ["Qt cleanup failed: Qt cleanup failed: cleanup injected"],
        "thread_stopped_before_window_delete": True,
    }


def test_baseline_stops_window_owned_thread_before_deleting_window(tmp_path: Path) -> None:
    receipt = _baseline_receipt("running_child", tmp_path)
    assert receipt == {
        "error": "GuiBaselineError",
        "closed": True,
        "deleted": True,
        "application_released": True,
        "notes": [],
        "thread_stopped_before_window_delete": True,
    }


def test_smoke_releases_qt_resources_after_window_exception(tmp_path: Path) -> None:
    marker_path = tmp_path / "smoke.marker"
    child_code = (
        "import atexit, json, runpy, sys; from pathlib import Path\n"
        f"sys.path.insert(0, {str(ROOT / 'src')!r})\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "from openai_tts_gui import gui\n"
        "original = gui.TTSWindow\n"
        "class ObservedWindow(original):\n"
        "    instance = None\n"
        "    def __init__(self):\n"
        "        super().__init__()\n"
        "        type(self).instance = self\n"
        "    def show(self):\n"
        "        raise RuntimeError('injected')\n"
        "    def close(self):\n"
        "        self.close_called = True\n"
        "        return super().close()\n"
        "    def deleteLater(self):\n"
        "        self.delete_later_called = True\n"
        "        return super().deleteLater()\n"
        "gui.TTSWindow = ObservedWindow\n"
        "atexit.register(\n"
        f"    lambda: Path({str(marker_path)!r}).write_text('normal', encoding='utf-8')\n"
        ")\n"
        f"entry = runpy.run_path({str(ENTRY_PATH)!r})\n"
        "try:\n"
        "    entry['_gui_smoke']()\n"
        "except RuntimeError as error:\n"
        "    window = ObservedWindow.instance\n"
        "    print(json.dumps({\n"
        "        'error': str(error),\n"
        "        'closed': getattr(window, 'close_called', False),\n"
        "        'deleted': getattr(window, 'delete_later_called', False),\n"
        "        'application_released': QApplication.instance() is None,\n"
        "    }))\n"
    )
    environment = _environment()
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
    assert marker_path.read_text(encoding="utf-8") == "normal"
    assert json.loads(result.stdout) == {
        "error": "injected",
        "closed": True,
        "deleted": True,
        "application_released": True,
    }
