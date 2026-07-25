from __future__ import annotations

import base64
import binascii
import logging
from itertools import cycle

from .. import config

logger = logging.getLogger(__name__)


def _xor_cipher(data: bytes, key: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, cycle(key)))


def encrypt_key(api_key: str) -> str:
    if not api_key:
        return ""
    key_bytes = api_key.encode("utf-8")
    encrypted_bytes = _xor_cipher(key_bytes, config.OBFUSCATION_KEY)
    return base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")


def decrypt_key(encrypted_key: str) -> str:
    if not encrypted_key:
        return ""
    try:
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode("utf-8"))
        decrypted_bytes = _xor_cipher(encrypted_bytes, config.OBFUSCATION_KEY)
        return decrypted_bytes.decode("utf-8")
    except (binascii.Error, UnicodeError):
        logger.error("Stored API key could not be decrypted.")
        return ""
