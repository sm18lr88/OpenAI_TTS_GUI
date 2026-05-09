import pytest

import openai_tts_gui.main as main


def test_main_starts_and_exits_cleanly(monkeypatch):
    # Avoid opening a real window or running a real event loop
    class DummySignal:
        def connect(self, _slot):
            pass

    class DummyApp:
        def __init__(self, argv):
            self.argv = argv

        def exec(self):
            return 0

    class DummyWin:
        def show(self):
            pass

    class DummyMessageBox:
        @staticmethod
        def critical(*args, **kwargs):
            return None

    class DummyPreflightWorker:
        def __init__(self, parent=None):
            self.parent = parent
            self.preflight_finished = DummySignal()
            self.finished = DummySignal()

        def deleteLater(self):
            pass

        def start(self):
            pass

    monkeypatch.setattr(main, "configure_logging", lambda: None)
    monkeypatch.setattr(
        main,
        "_load_gui_symbols",
        lambda: (
            DummyApp,
            DummyMessageBox,
            lambda app: None,
            DummyWin,
            DummyPreflightWorker,
        ),
    )

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0
