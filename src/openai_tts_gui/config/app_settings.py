from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from . import settings

logger = logging.getLogger(__name__)


def default_app_settings() -> dict[str, Any]:
    return {
        "parallelism": settings.PARALLELISM,
        "parallelism_warning_shown": False,
        "retain_files": False,
    }


def _resolve_filename(filename: str | None) -> Path:
    return Path(filename or settings.APP_SETTINGS_FILE)


def _clamp_parallelism(value: object) -> int:
    if isinstance(value, bool):
        return settings.PARALLELISM
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return settings.PARALLELISM
    else:
        return settings.PARALLELISM
    return max(1, min(8, parsed))


def load_app_settings(filename: str | None = None) -> dict[str, Any]:
    path = _resolve_filename(filename)
    defaults = default_app_settings()
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            logger.warning("App settings file %s did not contain a JSON object.", path)
            return defaults
        return {
            "parallelism": _clamp_parallelism(payload.get("parallelism", defaults["parallelism"])),
            "parallelism_warning_shown": bool(
                payload.get(
                    "parallelism_warning_shown",
                    defaults["parallelism_warning_shown"],
                )
            ),
            "retain_files": bool(payload.get("retain_files", defaults["retain_files"])),
        }
    except FileNotFoundError:
        logger.info("App settings file %s not found. Using defaults.", path)
        return defaults
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load app settings from %s: %s", path, exc)
        return defaults


def save_app_settings(app_settings: dict[str, Any], filename: str | None = None) -> bool:
    path = _resolve_filename(filename)
    temp_path: Path | None = None
    payload = {
        "parallelism": _clamp_parallelism(app_settings.get("parallelism")),
        "parallelism_warning_shown": bool(app_settings.get("parallelism_warning_shown", False)),
        "retain_files": bool(app_settings.get("retain_files", False)),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=path.stem + ".",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
        logger.info("Saved app settings to %s", path)
        return True
    except OSError as exc:
        logger.warning("Failed to save app settings to %s: %s", path, exc)
        return False
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
