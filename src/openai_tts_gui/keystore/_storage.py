from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from ..config import settings
from ._crypto import decrypt_key, encrypt_key

logger = logging.getLogger(__name__)

KEYRING_SERVICE_NAME = "OpenAI_TTS_GUI"
KEYRING_USERNAME = "OPENAI_API_KEY"

_keyring_mod: Any | None = None
_KEYRING_AVAILABLE = False
try:
    import keyring as _keyring_mod

    _KEYRING_AVAILABLE = True
except Exception:
    pass


def _resolve_filename(filename: str | None) -> Path:
    return Path(filename or settings.API_KEY_FILE)


def read_api_key(filename: str | None = None) -> str | None:
    api_key_env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    path = _resolve_filename(filename)

    if api_key_env:
        logger.info("Using API key from OPENAI_API_KEY environment variable.")
        return api_key_env

    if getattr(settings, "USE_KEYRING", False) and _KEYRING_AVAILABLE and _keyring_mod is not None:
        try:
            if hasattr(_keyring_mod, "get_password"):
                key = _keyring_mod.get_password("OpenAI_TTS_GUI", "OPENAI_API_KEY")
            else:
                key = None
            if key:
                logger.info("Using API key from OS keyring.")
                return key
        except Exception as exc:
            logger.warning("Keyring read failed: %s", exc)

    if not path.exists():
        logger.debug("API key file %s not found.", path)
        return None

    try:
        encrypted_key = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except IndexError:
        logger.warning("API key file %s is empty.", path)
        return None
    except OSError as exc:
        logger.exception("Error reading API key file %s: %s", path, exc)
        return None
    except Exception as exc:
        logger.exception("Unexpected error reading API key file %s: %s", path, exc)
        return None

    if not encrypted_key:
        logger.warning("API key file %s is empty.", path)
        return None

    decrypted_key = decrypt_key(encrypted_key)
    if decrypted_key:
        logger.debug("Read and decrypted API key from %s", path)
        return decrypted_key

    logger.error("Failed to decrypt API key from %s.", path)
    return None


def save_api_key(api_key: str, filename: str | None = None) -> bool:
    if not api_key:
        logger.warning("Attempted to save an empty API key. Aborting.")
        return False

    path = _resolve_filename(filename)
    keyring_ok = False

    if getattr(settings, "USE_KEYRING", False) and _KEYRING_AVAILABLE and _keyring_mod is not None:
        try:
            if hasattr(_keyring_mod, "set_password"):
                _keyring_mod.set_password("OpenAI_TTS_GUI", "OPENAI_API_KEY", api_key)
                keyring_ok = True
                logger.info("API key saved to OS keyring (OpenAI_TTS_GUI/OPENAI_API_KEY).")
        except Exception as exc:
            logger.warning("Failed to save API key to keyring: %s", exc)

    encrypted_key = encrypt_key(api_key)
    if not encrypted_key:
        logger.error("Failed to encrypt API key for saving.")
        return keyring_ok

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
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(encrypted_key + "\n")
        os.replace(temp_path, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
        logger.info("Encrypted API key saved to %s", path)
        return True
    except OSError as exc:
        logger.exception("Error saving API key to %s: %s", path, exc)
        return keyring_ok
    except Exception as exc:
        logger.exception("Unexpected error saving API key to %s: %s", path, exc)
        return keyring_ok
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
