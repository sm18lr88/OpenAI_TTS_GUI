from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from typing import Any

from .config.settings import (
    APP_NAME,
    LOG_FILE,
    LOGGING_FORMAT,
    LOGGING_LEVEL,
    ensure_directories,
)

logger = logging.getLogger(__name__)
_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    ensure_directories()
    formatter = logging.Formatter(LOGGING_FORMAT)

    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(LOGGING_LEVEL)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    _LOGGING_CONFIGURED = True


def _load_gui_symbols() -> tuple[Any, Any, Any, Any, Any]:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from .config.theme import apply_fusion_dark
    from .gui import TTSWindow

    return QApplication, QMessageBox, QTimer, apply_fusion_dark, TTSWindow


def run(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    logger.info("Starting %s application.", APP_NAME)

    args = list(argv) if argv is not None else sys.argv

    try:
        (
            QApplication,
            QMessageBox,
            QTimer,
            apply_fusion_dark,
            TTSWindow,
        ) = _load_gui_symbols()
    except ModuleNotFoundError as exc:
        logger.critical("GUI dependencies are not installed: %s", exc)
        print(
            "The GUI requires PyQt6 and related dependencies to be installed.",
            file=sys.stderr,
        )
        return 1

    try:
        app = QApplication(args)
        apply_fusion_dark(app)

        window = TTSWindow()
        window.show()
        logger.info("Main window displayed.")

        def run_post_show_checks() -> None:
            from .core.ffmpeg import preflight_check

            ok, detail = preflight_check()
            if ok:
                return
            QMessageBox.critical(window, "FFmpeg Missing/Outdated", detail)
            logger.critical(detail)
            app.exit(2)

        QTimer.singleShot(0, run_post_show_checks)
        return int(app.exec())
    except Exception as exc:
        logger.critical("An unhandled exception occurred: %s", exc, exc_info=True)
        return 1
    finally:
        logger.info("Exiting %s.", APP_NAME)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
