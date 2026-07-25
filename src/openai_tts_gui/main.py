from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from . import config
from .config import (
    GUI_LOG_MAX_BYTES,
    GUI_LOG_MAX_RECORD_BYTES,
    LOG_FILE,
    LOGGING_LEVEL,
    BoundedRotatingFileHandler,
    ensure_directories,
)

logger = logging.getLogger(__name__)
_LOGGING_CONFIGURED = False


def configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    ensure_directories()
    file_handler = BoundedRotatingFileHandler(
        LOG_FILE,
        max_bytes=GUI_LOG_MAX_BYTES,
        max_record_bytes=GUI_LOG_MAX_RECORD_BYTES,
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(LOGGING_LEVEL)
    root_logger.addHandler(file_handler)

    _LOGGING_CONFIGURED = True


def _load_gui_symbols():
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from .gui import FFmpegPreflightWorker, TTSWindow

    return QApplication, QMessageBox, config.apply_fusion_dark, TTSWindow, FFmpegPreflightWorker


def run(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    logger.info(
        "GUI application starting.",
        extra={"event": "gui.application.start", "outcome": "starting"},
    )

    args = list(argv) if argv is not None else sys.argv

    try:
        (
            QApplication,
            QMessageBox,
            apply_fusion_dark,
            TTSWindow,
            FFmpegPreflightWorker,
        ) = _load_gui_symbols()
    except ModuleNotFoundError as exc:
        logger.critical(
            "GUI dependencies are unavailable.",
            extra={
                "event": "gui.dependencies.unavailable",
                "outcome": "failed",
                "detail": str(exc),
            },
        )
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
        logger.info(
            "GUI main window displayed.",
            extra={"event": "gui.window.displayed", "outcome": "ready"},
        )

        def handle_preflight_result(ok: bool, detail: str) -> None:
            if ok:
                return
            QMessageBox.critical(window, "FFmpeg Missing/Outdated", detail)
            logger.critical(
                "GUI preflight failed.",
                extra={"event": "gui.preflight.failed", "outcome": "failed", "detail": detail},
            )
            app.exit(2)

        preflight_worker = FFmpegPreflightWorker(app)
        app._ffmpeg_preflight_worker = preflight_worker
        preflight_worker.preflight_finished.connect(handle_preflight_result)
        preflight_worker.finished.connect(preflight_worker.deleteLater)
        preflight_worker.finished.connect(lambda: setattr(app, "_ffmpeg_preflight_worker", None))
        preflight_worker.start()
        return int(app.exec())
    except OSError as exc:
        logger.critical(
            "GUI initialization failed.",
            extra={"event": "gui.initialization.failed", "outcome": "failed", "detail": str(exc)},
        )
        return 1
    finally:
        logger.info(
            "GUI application exiting.",
            extra={"event": "gui.application.exit", "outcome": "stopped"},
        )


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
