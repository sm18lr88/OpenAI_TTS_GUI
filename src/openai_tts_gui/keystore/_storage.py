from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol, assert_never, runtime_checkable

from keyring.errors import KeyringError

from .. import config
from ._crypto import decrypt_key
from ._outcomes import (
    CorruptLegacyCredential,
    CredentialReadOutcome,
    CredentialSaveOutcome,
    CredentialWarning,
    EmptyCredentialRejected,
    EmptyLegacyCredential,
    EnvironmentCredential,
    KeyringCredential,
    KeyringCredentialSaved,
    KeyringCredentialSaveFailed,
    KeyringCredentialUnavailable,
    KeyringReadFailureWarning,
    LegacyCredential,
    LegacyMigrationFailed,
    LegacyMigrationFailureWarning,
    LegacyMigrationNotAttempted,
    LegacyMigrationSucceeded,
    MissingCredential,
    StaleLegacyCredentialWarning,
    UnreadableLegacyCredential,
    credential_value,
)

logger = logging.getLogger(__name__)

KEYRING_SERVICE_NAME = "OpenAI_TTS_GUI"
KEYRING_USERNAME = "OPENAI_API_KEY"


@runtime_checkable
class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...


_keyring_mod = None
_KEYRING_AVAILABLE = False
try:
    import keyring

    _keyring_mod = keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _keyring_mod = None

settings = config.settings


def _resolve_filename(filename: str | None) -> Path:
    return Path(filename or settings.API_KEY_FILE)


def read_api_key_outcome(filename: str | None = None) -> CredentialReadOutcome:
    api_key_env = (os.environ.get("OPENAI_API_KEY") or "").strip()
    path = _resolve_filename(filename)

    if api_key_env:
        logger.info("Using API key from OPENAI_API_KEY environment variable.")
        return EnvironmentCredential(api_key_env)

    warning: tuple[CredentialWarning, ...] = ()
    keyring = _configured_keyring()
    if keyring is not None:
        try:
            key = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME)
            if key:
                logger.info("Using API key from OS keyring.")
                warnings = (StaleLegacyCredentialWarning(),) if path.is_file() else ()
                return KeyringCredential(key, warnings)
        except (KeyringError, OSError):
            logger.warning("Keyring credential lookup failed.")
            warning = (KeyringReadFailureWarning(),)

    return _read_legacy_credential(path, keyring, warning)


def read_api_key(filename: str | None = None) -> str | None:
    return credential_value(read_api_key_outcome(filename))


def save_api_key_outcome(api_key: str, filename: str | None = None) -> CredentialSaveOutcome:
    del filename
    if not api_key:
        logger.warning("Attempted to save an empty API key.")
        return EmptyCredentialRejected()

    keyring = _configured_keyring()
    if keyring is None:
        logger.warning("OS keyring is unavailable; credential was not saved.")
        return KeyringCredentialUnavailable()

    try:
        keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, api_key)
        logger.info("API key saved to OS keyring.")
        return KeyringCredentialSaved()
    except (KeyringError, OSError):
        logger.warning("OS keyring credential save failed.")
        return KeyringCredentialSaveFailed()


def save_api_key(api_key: str, filename: str | None = None) -> bool:
    outcome = save_api_key_outcome(api_key, filename)
    match outcome:
        case KeyringCredentialSaved():
            return True
        case (
            KeyringCredentialSaveFailed()
            | KeyringCredentialUnavailable()
            | EmptyCredentialRejected()
        ):
            return False
        case unreachable:
            assert_never(unreachable)


def _configured_keyring() -> KeyringBackend | None:
    if settings.USE_KEYRING and _KEYRING_AVAILABLE and isinstance(_keyring_mod, KeyringBackend):
        return _keyring_mod
    return None


def _read_legacy_credential(
    path: Path,
    keyring: KeyringBackend | None,
    warnings: tuple[CredentialWarning, ...],
) -> CredentialReadOutcome:
    try:
        legacy_bytes = path.read_bytes()
    except FileNotFoundError:
        return MissingCredential(warnings)
    except OSError:
        logger.warning("Legacy credential file could not be read.")
        return UnreadableLegacyCredential(warnings)

    try:
        encrypted_key = legacy_bytes.decode("utf-8").splitlines()[0].strip()
    except IndexError:
        return EmptyLegacyCredential(warnings)
    except UnicodeError:
        logger.warning("Legacy credential file is not UTF-8.")
        return CorruptLegacyCredential(warnings)

    if not encrypted_key:
        return EmptyLegacyCredential(warnings)

    decrypted_key = decrypt_key(encrypted_key)
    if not decrypted_key:
        return CorruptLegacyCredential(warnings)

    return _migrate_legacy_credential(decrypted_key, keyring, warnings)


def _migrate_legacy_credential(
    api_key: str,
    keyring: KeyringBackend | None,
    warnings: tuple[CredentialWarning, ...],
) -> LegacyCredential:
    if keyring is None:
        return LegacyCredential(api_key, LegacyMigrationNotAttempted(), warnings)
    try:
        keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_USERNAME, api_key)
    except (KeyringError, OSError):
        logger.warning("Legacy credential migration to OS keyring failed.")
        return LegacyCredential(
            api_key,
            LegacyMigrationFailed(),
            (*warnings, LegacyMigrationFailureWarning()),
        )
    logger.info("Legacy API key copied to OS keyring.")
    return LegacyCredential(api_key, LegacyMigrationSucceeded(), warnings)
