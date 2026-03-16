from openai_tts_gui import utils
from openai_tts_gui.config import settings
from openai_tts_gui.keystore import _storage as keystore_storage


def test_save_and_read_api_key_via_keyring(monkeypatch, tmp_path):
    store = {}

    class KR:
        @staticmethod
        def set_password(service, user, pwd):
            store[(service, user)] = pwd

        @staticmethod
        def get_password(service, user):
            return store.get((service, user))

    monkeypatch.setattr(keystore_storage, "keyring", KR)
    monkeypatch.setattr(keystore_storage, "_KEYRING_AVAILABLE", True)
    monkeypatch.setattr(settings, "USE_KEYRING", True)
    monkeypatch.setattr(settings, "API_KEY_FILE", str(tmp_path / "api_key.enc"))

    assert utils.save_api_key("sk-unit-xyz")
    assert utils.read_api_key() == "sk-unit-xyz"


def test_file_fallback_encrypt_decrypt(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_KEYRING", False)
    keyfile = tmp_path / "api_key.enc"
    monkeypatch.setattr(settings, "API_KEY_FILE", str(keyfile))

    assert utils.save_api_key("sk-file-abc")
    got = utils.read_api_key()
    assert got == "sk-file-abc"
    raw = keyfile.read_text(encoding="utf-8").strip()
    assert "sk-file-abc" not in raw
