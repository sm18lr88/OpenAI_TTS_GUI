import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMessageBox

from openai_tts_gui.gui import TTSWindow


def test_close_event_defers_slow_tts_cancellation_without_worker_signal(qtbot, monkeypatch):
    class DummySignal:
        def __init__(self):
            self.slot = None

        def connect(self, slot):
            self.slot = slot

    class SlowWorker:
        def __init__(self):
            self.cancelled = False
            self.finished = DummySignal()

        def isRunning(self):
            return True

        def cancel(self):
            self.cancelled = True

        def wait(self, _timeout):
            return False

    # Given: a visible window with a running worker that cannot stop immediately.
    window = TTSWindow()
    qtbot.addWidget(window)
    window.show()
    worker = SlowWorker()
    window.tts_processor = worker
    monkeypatch.setattr(
        "openai_tts_gui.gui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    # When: the close event is accepted by the user.
    event = QCloseEvent()
    window.closeEvent(event)

    # Then: cancellation is requested and a single event-loop retry is scheduled.
    assert worker.cancelled is True
    assert event.isAccepted() is False
    assert window._close_after_tts_cancel is True
    assert window._close_retry_timer is not None
    window.tts_processor = None
    window.close()
