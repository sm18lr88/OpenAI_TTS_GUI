import logging
import os
from pathlib import Path
from typing import Any

from ..config import settings
from ._crypto import decrypt_key, encrypt_key

logger = logging.getLogger(__name__)

keyring: Any | None
try:
    import keyring

    _KEYRING_AVAILABLE = True
except Exception:
    keyring = None
    _KEYRING_AVAILABLE = False


def read_api_key(filename: str | None = None) -> str | None:
    api_key_env = os.environ.get("OPENAI_API_KEY")
    filename = filename or settings.API_KEY_FILE
    if api_key_env:
        logger.info("Using API key from OPENAI_API_KEY environment variable.")
        return api_key_env

    if getattr(settings, "USE_KEYRING", False) and _KEYRING_AVAILABLE and keyring is not None:
        try:
            if hasattr(keyring, "get_password"):
                key = keyring.get_password("OpenAI_TTS_GUI", "OPENAI_API_KEY")
            else:
                key = None
            if key:
                logger.info("Using API key from OS keyring.")
                return key
        except Exception as e:
            logger.warning(f"Keyring read failed: {e}")

    if not os.path.exists(filename):
        logger.warning(f"API key file '{filename}' not found.")
        return None

    try:
        with open(filename, encoding="utf-8") as file:
            encrypted_key = file.readline().strip()
        if not encrypted_key:
            logger.warning(f"API key file '{filename}' is empty.")
            return None

        decrypted_key = decrypt_key(encrypted_key)
        if decrypted_key:
            logger.debug(f"Read and decrypted API key from {filename}")
            return decrypted_key
        else:
            logger.error(f"Failed to decrypt API key from {filename}.")
            return None
    except OSError as e:
        logger.exception(f"Error reading API key file {filename}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error reading API key file {filename}: {e}")
        return None


def save_api_key(api_key: str, filename: str | None = None) -> bool:
    if not api_key:
        logger.warning("Attempted to save an empty API key. Aborting.")
        return False
    filename = filename or settings.API_KEY_FILE
    keyring_ok = False
    if getattr(settings, "USE_KEYRING", False) and _KEYRING_AVAILABLE and keyring is not None:
        try:
            if hasattr(keyring, "set_password"):
                keyring.set_password("OpenAI_TTS_GUI", "OPENAI_API_KEY", api_key)
                keyring_ok = True
                logger.info("API key saved to OS keyring (OpenAI_TTS_GUI/OPENAI_API_KEY).")
        except Exception as e:
            logger.warning(f"Failed to save API key to keyring: {e}")

    encrypted_key = encrypt_key(api_key)
    if not encrypted_key:
        logger.error("Failed to encrypt API key for saving.")
        return keyring_ok
    try:
        parent = Path(filename).parent
        if str(parent):
            os.makedirs(parent, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as file:
            file.write(encrypted_key + "\n")
        logger.info(f"Encrypted API key saved to {filename}")
        file_ok = True
        return file_ok or keyring_ok
    except OSError as e:
        logger.exception(f"Error saving API key to {filename}: {e}")
        return keyring_ok
    except Exception as e:
        logger.exception(f"Unexpected error saving API key to {filename}: {e}")
        return keyring_ok
