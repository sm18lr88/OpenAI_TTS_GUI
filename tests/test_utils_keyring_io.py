import config
import utils


def test_save_and_read_api_key_via_keyring(monkeypatch, tmp_path):
    # Fake keyring in-memory
    store = {}

    class KR:
        @staticmethod
        def set_password(service, user, pwd):
            store[(service, user)] = pwd

        @staticmethod
        def get_password(service, user):
            return store.get((service, user))

    monkeypatch.setattr(utils, "keyring", KR)
    monkeypatch.setattr(config, "USE_KEYRING", True)
    monkeypatch.setattr(config, "API_KEY_FILE", str(tmp_path / "api_key.enc"))

    assert utils.save_api_key("sk-unit-xyz")
    assert utils.read_api_key() == "sk-unit-xyz"


def test_file_fallback_encrypt_decrypt(monkeypatch, tmp_path):
    # Disable keyring to force file path
    monkeypatch.setattr(config, "USE_KEYRING", False)
    keyfile = tmp_path / "api_key.enc"
    monkeypatch.setattr(config, "API_KEY_FILE", str(keyfile))

    # Save then read back (file path)
    assert utils.save_api_key("sk-file-abc")
    got = utils.read_api_key()
    assert got == "sk-file-abc"
    # Ensure file content isn't plaintext
    raw = keyfile.read_text(encoding="utf-8").strip()
    assert "sk-file-abc" not in raw
