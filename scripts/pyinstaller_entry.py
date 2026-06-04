import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from openai_tts_gui.main import main


def _self_check() -> int:
    from openai_tts_gui.config import settings

    snap = settings.env_snapshot()
    print(f"{settings.APP_NAME} {settings.APP_VERSION}")
    print(f"python={snap.get('python', 'unknown')}")
    print(f"platform={snap.get('platform', 'unknown')}")
    print(f"openai={snap.get('openai', 'unknown')}")
    print(f"pyqt6={snap.get('pyqt6', 'unknown')}")
    return 0


def _gui_smoke() -> int:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from openai_tts_gui.config.theme import apply_fusion_dark
    from openai_tts_gui.gui import TTSWindow

    app = QApplication(sys.argv[:1])
    apply_fusion_dark(app)
    window = TTSWindow()
    window.show()
    app.processEvents()
    QTimer.singleShot(0, app.quit)
    result = int(app.exec())
    window.close()
    print("gui-smoke=ok")
    return result


if __name__ == "__main__":
    if "--self-check" in sys.argv[1:]:
        raise SystemExit(_self_check())
    if "--gui-smoke" in sys.argv[1:]:
        raise SystemExit(_gui_smoke())
    main()
