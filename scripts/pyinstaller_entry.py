import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from openai_tts_gui.main import main


class GuiSmokeError(Exception):
    pass


def _self_check() -> int:
    from openai_tts_gui.config import settings

    snap = settings.env_snapshot()
    print(f"{settings.APP_NAME} {settings.APP_VERSION}")
    print(f"python={snap.get('python', 'unknown')}")
    print(f"platform={snap.get('platform', 'unknown')}")
    print(f"openai={snap.get('openai', 'unknown')}")
    print(f"pyqt6={snap.get('pyqt6', 'unknown')}")
    return 0


def _teardown_gui_smoke(app, window) -> None:
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, QThread

    failure = None
    for thread in window.findChildren(QThread):
        if not sip.isdeleted(thread) and thread.isRunning():
            thread.quit()
            if not thread.wait(1000):
                failure = RuntimeError("Window-owned QThread did not stop")
    if failure is not None:
        raise GuiSmokeError("GUI smoke cleanup failed") from failure
    try:
        window.close()
    except RuntimeError as error:
        failure = error
    try:
        window.deleteLater()
    except RuntimeError as error:
        failure = failure or error
    try:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    except RuntimeError as error:
        failure = failure or error
    if app.topLevelWidgets():
        raise GuiSmokeError("GUI smoke left top-level widgets behind")
    if failure is not None:
        raise GuiSmokeError("GUI smoke cleanup failed") from failure


def _release_gui_smoke_application(app) -> None:
    from PyQt6 import sip

    if not sip.isdeleted(app):
        app.quit()
        sip.delete(app)


def _gui_smoke(screenshot_path: str | None = None) -> int:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from openai_tts_gui.config.theme import apply_fusion_dark
    from openai_tts_gui.gui import TTSWindow

    app = QApplication(sys.argv[:1])
    window = None
    result = 1
    try:
        apply_fusion_dark(app)
        window = TTSWindow()
        window.show()
        app.processEvents()
        if screenshot_path is None or window.grab().save(screenshot_path):
            QTimer.singleShot(0, app.quit)
            result = int(app.exec())
    finally:
        primary_error = sys.exception()
        if primary_error is None:
            try:
                if window is not None:
                    _teardown_gui_smoke(app, window)
            finally:
                _release_gui_smoke_application(app)
        else:
            if window is not None:
                try:
                    _teardown_gui_smoke(app, window)
                except GuiSmokeError as cleanup_error:
                    primary_error.add_note(f"Qt cleanup failed: {cleanup_error}")
            try:
                _release_gui_smoke_application(app)
            except RuntimeError as cleanup_error:
                primary_error.add_note(f"Qt cleanup failed: {cleanup_error}")
        window = None
        app = None
    if result == 0:
        print("gui-smoke=ok")
    return result


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if "--self-check" in arguments:
        raise SystemExit(_self_check())
    if "--gui-smoke" in arguments:
        smoke_index = arguments.index("--gui-smoke")
        screenshot_path = arguments[smoke_index + 1] if smoke_index + 1 < len(arguments) else None
        raise SystemExit(_gui_smoke(screenshot_path))
    main()
