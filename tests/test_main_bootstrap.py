import openai_tts_gui.main as main
import pytest


def test_main_starts_and_exits_cleanly(monkeypatch):
    # Avoid opening a real window or running a real event loop
    class DummyApp:
        def __init__(self, argv):
            pass

        def exec(self):
            return 0

    class DummyWin:
        def show(self):
            pass

    monkeypatch.setattr(main, "QApplication", DummyApp)
    monkeypatch.setattr(main, "TTSWindow", DummyWin)
    monkeypatch.setattr(main, "preflight_check", lambda: (True, "ffmpeg OK"))
    monkeypatch.setattr(main, "setTheme", lambda *a, **k: None)

    # Capture sys.exit
    with pytest.raises(SystemExit) as e:
        main.main()
    assert e.value.code == 0
