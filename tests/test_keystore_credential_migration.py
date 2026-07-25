from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from keyring.errors import KeyringError

from openai_tts_gui.config import settings
from openai_tts_gui.keystore import (
    CorruptLegacyCredential,
    CredentialSource,
    EmptyCredentialRejected,
    EmptyLegacyCredential,
    EnvironmentCredential,
    KeyringCredential,
    KeyringCredentialSaved,
    KeyringCredentialSaveFailed,
    KeyringCredentialUnavailable,
    LegacyCredential,
    LegacyMigrationFailed,
    LegacyMigrationSucceeded,
    StaleLegacyCredentialWarning,
    _crypto,
    _storage,
    read_api_key,
    read_api_key_outcome,
    save_api_key,
    save_api_key_outcome,
)


class MemoryKeyring:
    def __init__(self, value: str | None = None, write_error: bool = False) -> None:
        self.value = value
        self.write_error = write_error
        self.reads = 0
        self.writes = 0
        self.identifiers: list[tuple[str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        self.reads += 1
        self.identifiers.append((service, username))
        return self.value

    def set_password(self, service: str, username: str, password: str) -> None:
        self.writes += 1
        self.identifiers.append((service, username))
        if self.write_error:
            raise KeyringError("synthetic write failure")
        self.value = password


@pytest.fixture
def credential_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "credentials" / "api_key.enc"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "API_KEY_FILE", str(path))
    monkeypatch.setattr(settings, "USE_KEYRING", True)
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", True)
    return path


def write_legacy_credential(path: Path, value: str = "synthetic-legacy-credential") -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (_crypto.encrypt_key(value) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_read_outcome_prefers_environment_without_migrating_legacy(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: both a legacy credential and an empty keyring exist.
    legacy_bytes = write_legacy_credential(credential_path)
    keyring = MemoryKeyring()
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-credential")

    # When: the public typed facade reads the credential.
    outcome = read_api_key_outcome()

    # Then: the environment wins without touching either legacy storage or keyring.
    assert outcome == EnvironmentCredential("synthetic-environment-credential")
    assert credential_path.read_bytes() == legacy_bytes
    assert keyring.reads == 0
    assert keyring.writes == 0
    assert read_api_key() == "synthetic-environment-credential"


def test_read_outcome_prefers_keyring_and_leaves_legacy_bytes_untouched(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: keyring and legacy storage contain different synthetic credentials.
    legacy_bytes = write_legacy_credential(credential_path)
    keyring = MemoryKeyring("synthetic-keyring-credential")
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)

    # When: the public typed facade reads the credential.
    outcome = read_api_key_outcome()

    # Then: keyring wins and legacy storage is not rewritten or deleted.
    assert isinstance(outcome, KeyringCredential)
    assert outcome.api_key == "synthetic-keyring-credential"
    assert credential_path.read_bytes() == legacy_bytes
    assert keyring.reads == 1
    assert keyring.writes == 0


def test_valid_legacy_credential_is_copied_once_to_empty_keyring_without_mutation(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an empty keyring and a valid legacy credential with known bytes.
    legacy_bytes = write_legacy_credential(credential_path)
    legacy_hash = digest(legacy_bytes)
    keyring = MemoryKeyring()
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)

    # When: the typed facade reads the legacy credential.
    outcome = read_api_key_outcome()

    # Then: the legacy value is returned, copied once, and its bytes remain identical.
    assert isinstance(outcome, LegacyCredential)
    assert outcome.api_key == "synthetic-legacy-credential"
    assert outcome.migration == LegacyMigrationSucceeded()
    assert digest(credential_path.read_bytes()) == legacy_hash
    assert keyring.reads == 1
    assert keyring.writes == 1
    assert keyring.identifiers == [
        ("OpenAI_TTS_GUI", "OPENAI_API_KEY"),
        ("OpenAI_TTS_GUI", "OPENAI_API_KEY"),
    ]


def test_failed_legacy_migration_returns_legacy_value_with_typed_warning(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a valid legacy credential and a keyring that rejects migration writes.
    legacy_bytes = write_legacy_credential(credential_path)
    keyring = MemoryKeyring(write_error=True)
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)

    # When: the typed facade attempts migration.
    outcome = read_api_key_outcome()

    # Then: access survives and the migration warning is typed without mutating the legacy file.
    assert isinstance(outcome, LegacyCredential)
    assert outcome.api_key == "synthetic-legacy-credential"
    assert outcome.migration == LegacyMigrationFailed()
    assert credential_path.read_bytes() == legacy_bytes
    assert keyring.writes == 1


@pytest.mark.parametrize(
    ("content", "expected_type"),
    [
        (b"", EmptyLegacyCredential),
        (b"  \n", EmptyLegacyCredential),
        (b"not-base64%\n", CorruptLegacyCredential),
        (b"\xff", CorruptLegacyCredential),
    ],
)
def test_legacy_empty_and_corrupt_bytes_produce_typed_read_outcomes(
    credential_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    expected_type: type[EmptyLegacyCredential] | type[CorruptLegacyCredential],
) -> None:
    # Given: keyring is empty and the legacy file contains an invalid byte fixture.
    credential_path.parent.mkdir(parents=True)
    credential_path.write_bytes(content)
    monkeypatch.setattr(_storage, "_keyring_mod", MemoryKeyring())

    # When: the typed facade reads the credential.
    outcome = read_api_key_outcome()

    # Then: the exact legacy condition is retained instead of being collapsed into None.
    assert isinstance(outcome, expected_type)
    assert read_api_key() is None


def test_new_save_uses_keyring_only_and_legacy_file_is_never_created(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: an available empty keyring and no legacy credential path.
    keyring = MemoryKeyring()
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)

    # When: the typed save facade receives a new credential.
    outcome = save_api_key_outcome("synthetic-new-credential")

    # Then: only keyring receives it and the scalar projection remains true.
    assert outcome == KeyringCredentialSaved()
    assert keyring.value == "synthetic-new-credential"
    assert not credential_path.exists()
    assert save_api_key("synthetic-newer-credential")
    assert not credential_path.exists()


def test_keyring_save_failure_never_creates_legacy_file(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: keyring rejects all saves and no legacy path exists.
    keyring = MemoryKeyring(write_error=True)
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)

    # When: the typed save facade receives a credential.
    outcome = save_api_key_outcome("synthetic-new-credential")

    # Then: failure is typed, the scalar projection is false, and no fallback file appears.
    assert outcome == KeyringCredentialSaveFailed()
    assert not save_api_key("synthetic-newer-credential")
    assert not credential_path.exists()


def test_empty_save_is_rejected_without_touching_keyring_or_legacy_file(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyring = MemoryKeyring()
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)

    outcome = save_api_key_outcome("")

    assert outcome == EmptyCredentialRejected()
    assert keyring.writes == 0
    assert not credential_path.exists()


def test_save_reports_unavailable_keyring_without_creating_legacy_file(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", False)
    monkeypatch.setattr(_storage, "_keyring_mod", None)

    outcome = save_api_key_outcome("synthetic-new-credential")

    assert outcome == KeyringCredentialUnavailable()
    assert not credential_path.exists()


def test_keyring_credential_warns_when_a_stale_legacy_file_remains(
    credential_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a newly saved keyring credential and an older untouched legacy file.
    legacy_bytes = write_legacy_credential(credential_path)
    keyring = MemoryKeyring()
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)
    assert save_api_key_outcome("synthetic-new-credential") == KeyringCredentialSaved()

    # When: the keyring-backed credential is read.
    outcome = read_api_key_outcome()

    # Then: callers receive manual-removal guidance while the old file remains byte-identical.
    assert isinstance(outcome, KeyringCredential)
    assert outcome.source is CredentialSource.KEYRING
    assert outcome.warnings == (StaleLegacyCredentialWarning(),)
    assert credential_path.read_bytes() == legacy_bytes
