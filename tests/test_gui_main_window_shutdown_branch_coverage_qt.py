from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMessageBox

from openai_tts_gui.gui import TTSWindow


class _DeferredWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, *, cancellation: bool) -> None:
        super().__init__()
        self.cancellation = cancellation
        self.cancelled = False
        self.wait_calls = 0
        self.running = True

    def isRunning(self) -> bool:
        return self.running

    def wait(self, _milliseconds: int) -> bool:
        self.wait_calls += 1
        raise AssertionError("closeEvent must not synchronously wait")

    def cancel(self) -> None:
        self.cancelled = True


def _window(qtbot) -> TTSWindow:
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    return window


def test_close_defers_for_active_api_loader_without_wait_and_eventually_closes(qtbot) -> None:
    window = _window(qtbot)
    loader = _DeferredWorker(cancellation=False)
    window._api_key_loader = loader
    first = QCloseEvent()
    second = QCloseEvent()

    window.closeEvent(first)
    window.closeEvent(second)

    assert not first.isAccepted()
    assert not second.isAccepted()
    assert window._close_after_api_key_load
    assert loader.wait_calls == 0
    assert (
        window.statusBar().currentMessage() == "Waiting for the API key to load before closing..."
    )
    loader.running = False
    loader.finished.emit()
    qtbot.waitUntil(lambda: not window.isVisible())


def test_close_defers_for_active_tts_after_user_confirms_without_wait_and_eventually_closes(
    qtbot, monkeypatch
) -> None:
    window = _window(qtbot)
    worker = _DeferredWorker(cancellation=True)
    window.tts_processor = worker
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    first = QCloseEvent()
    second = QCloseEvent()

    window.closeEvent(first)
    window.closeEvent(second)

    assert worker.cancelled
    assert not first.isAccepted()
    assert not second.isAccepted()
    assert window._close_after_tts_cancel
    assert worker.wait_calls == 0
    assert (
        window.statusBar().currentMessage()
        == "Waiting for TTS cancellation to finish before closing..."
    )
    worker.running = False
    worker.finished.emit()
    qtbot.waitUntil(lambda: not window.isVisible())


def test_startup_does_not_launch_api_key_loader_after_window_closes(qtbot, monkeypatch) -> None:
    window = _window(qtbot)
    loader_starts: list[bool] = []
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        window,
        "_start_api_key_load",
        lambda *, notify_on_result: loader_starts.append(notify_on_result),
    )

    window.close()
    window._finish_startup()

    assert loader_starts == []
