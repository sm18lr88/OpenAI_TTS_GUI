from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)


def _resolve_filename(filename: str | None) -> Path:
    return Path(filename or settings.PRESETS_FILE)


def load_presets(filename: str | None = None) -> dict[str, str]:
    path = _resolve_filename(filename)
    try:
        with path.open(encoding="utf-8") as file:
            presets = json.load(file)
        if not isinstance(presets, dict):
            logger.warning("Presets file %s did not contain a JSON object.", path)
            return {}

        cleaned: dict[str, str] = {}
        for key, value in presets.items():
            if isinstance(key, str) and isinstance(value, str):
                cleaned[key] = value
            else:
                logger.warning("Ignoring invalid preset entry %r in %s", key, path)

        logger.info("Loaded %d presets from %s", len(cleaned), path)
        return cleaned
    except FileNotFoundError:
        logger.info("Presets file %s not found. Returning empty dictionary.", path)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("Error decoding JSON from %s: %s. Returning empty dictionary.", path, exc)
        return {}
    except OSError as exc:
        logger.exception(
            "Error reading presets file %s: %s. Returning empty dictionary.",
            path,
            exc,
        )
        return {}
    except Exception as exc:
        logger.exception(
            "Unexpected error loading presets from %s: %s. Returning empty dictionary.",
            path,
            exc,
        )
        return {}


def save_presets(presets: dict[str, str], filename: str | None = None) -> bool:
    path = _resolve_filename(filename)
    temp_path: Path | None = None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=path.stem + ".",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as file:
            temp_path = Path(file.name)
            json.dump(presets, file, indent=2, ensure_ascii=False, sort_keys=True)
            file.write("\n")
        os.replace(temp_path, path)
        logger.info("Saved %d presets to %s", len(presets), path)
        return True
    except OSError as exc:
        logger.exception("Error writing presets to %s: %s", path, exc)
        return False
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
