from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QThread
from PyQt6.QtWidgets import QApplication, QWidget


class GuiLifecycleError(Exception):
    pass


def release_qt_resources(
    app: QApplication, window: QWidget | None, threads: tuple[QThread, ...] = ()
) -> tuple[str, ...]:
    failures: list[str] = []
    owned_threads = {id(thread): thread for thread in threads if not sip.isdeleted(thread)}
    if window is not None and not sip.isdeleted(window):
        owned_threads.update(
            {
                id(thread): thread
                for thread in window.findChildren(QThread)
                if not sip.isdeleted(thread)
            }
        )
    for thread in owned_threads.values():
        try:
            if thread.isRunning():
                thread.quit()
                if not thread.wait(1000):
                    failures.append("Window-owned QThread did not stop")
        except RuntimeError as error:
            failures.append(str(error))
    remaining: tuple[str, ...] = ()
    threads_stopped = not failures
    if threads_stopped and window is not None and not sip.isdeleted(window):
        try:
            window.close()
        except RuntimeError as error:
            failures.append(str(error))
        try:
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        except RuntimeError as error:
            failures.append(str(error))
    if threads_stopped and not sip.isdeleted(app):
        remaining = tuple(widget.objectName() for widget in app.topLevelWidgets())
        app.quit()
        sip.delete(app)
    if failures:
        raise GuiLifecycleError(f"Qt cleanup failed: {failures[0]}")
    return remaining
