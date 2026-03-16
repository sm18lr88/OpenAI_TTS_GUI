import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from . import config
from .config.theme import apply_fusion_dark
from .core.ffmpeg import preflight_check
from .gui import TTSWindow


class _DummyTheme:
    DARK = "dark"
    LIGHT = "light"


def setTheme(*_args, **_kwargs):
    return None


Theme = _DummyTheme()

config.ensure_directories()

logging.basicConfig(
    level=config.LOGGING_LEVEL,
    format=config.LOGGING_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def main():
    logger.info(f"Starting {config.APP_NAME} application.")
    app = QApplication(sys.argv)

    apply_fusion_dark(app)
    setTheme(Theme.DARK)

    try:
        ok, detail = preflight_check()
        if not ok:
            QMessageBox.critical(None, "FFmpeg Missing/Outdated", detail)
            logger.critical(detail)
            sys.exit(2)
        window = TTSWindow()
        window.show()
        logger.info("Main window displayed.")
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        # Optionally show a critical error message to the user here
        # QMessageBox.critical(
        #     None,
        #     "Fatal Error",
        #     f"A critical error occurred: {e}\nPlease check the log file.",
        # )
        sys.exit(1)  # Exit with error code
    finally:
        logger.info(f"Exiting {config.APP_NAME}.")


if __name__ == "__main__":
    main()
