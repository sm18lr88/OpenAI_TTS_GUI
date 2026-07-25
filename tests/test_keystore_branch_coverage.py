from pathlib import Path

import pytest
from keyring.errors import KeyringError

from openai_tts_gui.config import settings
from openai_tts_gui.keystore import _crypto, _storage


class _InjectedUnexpectedReadError(Exception):
    pass


class _Keyring:
    def __init__(
        self,
        value: str | None = None,
        *,
        fail_read: bool = False,
        fail_write: bool = False,
    ) -> None:
        self.value = value
        self.calls: list[tuple[str, str, str | None]] = []
        self.fail_read = fail_read
        self.fail_write = fail_write

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append((service, username, None))
        if self.fail_read:
            raise OSError("read failure")
        return self.value

    def set_password(self, service: str, username: str, password: str) -> None:
        self.calls.append((service, username, password))
        if self.fail_write:
            raise OSError("write failure")
        self.value = password


class _KeyringErrorBackend:
    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringError("keyring read failure")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringError("keyring write failure")


@pytest.fixture
def key_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "keys" / "api_key.enc"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "API_KEY_FILE", str(path))
    monkeypatch.setattr(settings, "USE_KEYRING", False)
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", False)
    monkeypatch.setattr(_storage, "_keyring_mod", None)
    return path


@pytest.mark.parametrize("api_key", ["", "sk-ascii", "cafe-東京-λ"])
def test_crypto_round_trip_and_empty_input(api_key: str) -> None:
    encrypted = _crypto.encrypt_key(api_key)
    assert _crypto.decrypt_key(encrypted) == api_key


def test_crypto_rejects_corrupt_input_and_surfaces_unexpected_cipher_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _crypto.decrypt_key("not valid base64%") == ""

    def fail_cipher(data: bytes, key: bytes) -> bytes:
        raise OSError("cipher failure")

    monkeypatch.setattr(_crypto, "_xor_cipher", fail_cipher)
    with pytest.raises(OSError, match="cipher failure"):
        _crypto.encrypt_key("sk-fail")
    with pytest.raises(OSError, match="cipher failure"):
        _crypto.decrypt_key("c2s=")


def test_read_prefers_environment_then_keyring(
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = _Keyring("keyring-key")
    monkeypatch.setattr(settings, "USE_KEYRING", True)
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", True)
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)
    key_file.parent.mkdir()
    key_file.write_text(_crypto.encrypt_key("file-key") + "\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", " env-key ")
    assert _storage.read_api_key() == "env-key"
    assert keyring.calls == []
    monkeypatch.delenv("OPENAI_API_KEY")
    assert _storage.read_api_key() == "keyring-key"
    assert keyring.calls == [("OpenAI_TTS_GUI", "OPENAI_API_KEY", None)]


@pytest.mark.parametrize("content", ["", "  \n", "not base64%\n"])
def test_read_file_fallback_rejects_empty_and_corrupt_content(
    key_file: Path,
    content: str,
) -> None:
    key_file.parent.mkdir()
    key_file.write_text(content, encoding="utf-8")
    assert _storage.read_api_key() is None


def test_read_falls_back_after_keyring_failure_and_file_errors(
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = _Keyring(fail_read=True)
    monkeypatch.setattr(settings, "USE_KEYRING", True)
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", True)
    monkeypatch.setattr(_storage, "_keyring_mod", keyring)
    key_file.parent.mkdir()
    key_file.write_text(_crypto.encrypt_key("file-key") + "\n", encoding="utf-8")
    assert _storage.read_api_key() == "file-key"

    def fail_read(self: Path) -> bytes:
        raise PermissionError("read failure")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    assert _storage.read_api_key() is None


def test_keyring_error_falls_back_to_encrypted_file(
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file.parent.mkdir()
    key_file.write_text(_crypto.encrypt_key("file-key") + "\n", encoding="utf-8")
    monkeypatch.setattr(settings, "USE_KEYRING", True)
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", True)
    monkeypatch.setattr(_storage, "_keyring_mod", _KeyringErrorBackend())

    assert _storage.read_api_key() == "file-key"


def test_read_handles_missing_keyring_method_and_surfaces_unexpected_read_error(
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USE_KEYRING", True)
    monkeypatch.setattr(_storage, "_KEYRING_AVAILABLE", True)
    monkeypatch.setattr(_storage, "_keyring_mod", object())
    assert _storage.read_api_key() is None
    key_file.parent.mkdir()
    key_file.write_text("valid-looking\n", encoding="utf-8")

    def fail_read(self: Path) -> bytes:
        raise _InjectedUnexpectedReadError("unexpected read failure")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(_InjectedUnexpectedReadError, match="unexpected read failure"):
        _storage.read_api_key()
