import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from . import config
from .gui import TTSWindow
from .utils import preflight_check


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
# Silence overly chatty httpx/openai debug logs unless explicitly enabled
# import logging as _logging; _logging.getLogger("httpx").setLevel(_logging.WARNING)

logger = logging.getLogger(__name__)  # Get logger for main module


# --- Main Execution ---
def main():
    logger.info(f"Starting {config.APP_NAME} application.")
    app = QApplication(sys.argv)

    # Keep a harmless call so older code/tests can patch it; does nothing here.
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
