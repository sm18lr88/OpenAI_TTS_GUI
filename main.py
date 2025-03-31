import sys
import logging
from PyQt6.QtWidgets import QApplication

# Set up configuration first
import config

# Now import GUI after config is available
from gui import TTSWindow

# --- Logging Setup ---
# Basic configuration (can be enhanced with rotation, etc.)
logging.basicConfig(
    level=config.LOGGING_LEVEL,
    format=config.LOGGING_FORMAT,
    handlers=[
        logging.FileHandler(config.LOG_FILE, mode="a", encoding="utf-8"),  # Log to file
        logging.StreamHandler(sys.stdout),  # Also log to console
    ],
)
# Suppress overly verbose logs from libraries if needed
# logging.getLogger("urllib3").setLevel(logging.WARNING)
# logging.getLogger("openai").setLevel(logging.INFO)

logger = logging.getLogger(__name__)  # Get logger for main module


# --- Main Execution ---
def main():
    logger.info(f"Starting {config.APP_NAME} application.")
    app = QApplication(sys.argv)

    try:
        window = TTSWindow()
        window.show()
        logger.info("Main window displayed.")
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"An unhandled exception occurred: {e}", exc_info=True)
        # Optionally show a critical error message to the user here
        # QMessageBox.critical(None, "Fatal Error", f"A critical error occurred: {e}\nPlease check the log file.")
        sys.exit(1)  # Exit with error code
    finally:
        logger.info(f"Exiting {config.APP_NAME}.")


if __name__ == "__main__":
    main()
