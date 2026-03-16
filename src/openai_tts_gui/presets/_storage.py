import json
import logging

from ..config import settings

logger = logging.getLogger(__name__)


def load_presets(filename=settings.PRESETS_FILE) -> dict:
    try:
        with open(filename, encoding="utf-8") as file:
            presets = json.load(file)
        logger.info(f"Loaded {len(presets)} presets from {filename}")
        return presets if isinstance(presets, dict) else {}
    except FileNotFoundError:
        logger.info(f"Presets file '{filename}' not found. Returning empty dictionary.")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {filename}: {e}. Returning empty dictionary.")
        return {}
    except OSError as e:
        logger.exception(f"Error reading presets file {filename}: {e}. Returning empty dictionary.")
        return {}
    except Exception as e:
        logger.exception(
            f"Unexpected error loading presets from {filename}: {e}. Returning empty dictionary."
        )
        return {}


def save_presets(presets: dict, filename=settings.PRESETS_FILE):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(presets, file, indent=4)
        logger.info(f"Saved {len(presets)} presets to {filename}")
        return True
    except OSError as e:
        logger.exception(f"Error writing presets to {filename}: {e}")
        return False
