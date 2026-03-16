"""Backward compatibility tests.

These tests pin the exact constants, environment variable names, keyring
service/username strings, and data-format behaviour that external tooling or
saved user data may depend on. They must PASS without any architecture changes
and must continue to pass after the refactor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openai_tts_gui import config
from openai_tts_gui.utils import decrypt_key, encrypt_key, load_presets, save_presets


def test_obfuscation_key_value():
    assert config.OBFUSCATION_KEY == b"my_simple_secret_key_for_xor"


def test_keyring_service_name():
    source = (
        Path(__file__).resolve().parents[1] / "src" / "openai_tts_gui" / "utils.py"
    ).read_text(encoding="utf-8")
    assert '"OpenAI_TTS_GUI"' in source, (
        "Keyring service name 'OpenAI_TTS_GUI' must appear in utils.py"
    )


def test_keyring_username():
    source = (
        Path(__file__).resolve().parents[1] / "src" / "openai_tts_gui" / "utils.py"
    ).read_text(encoding="utf-8")
    assert '"OPENAI_API_KEY"' in source, "Keyring username 'OPENAI_API_KEY' must appear in utils.py"


def test_env_var_names():
    utils_source = (
        Path(__file__).resolve().parents[1] / "src" / "openai_tts_gui" / "utils.py"
    ).read_text(encoding="utf-8")
    config_source = (
        Path(__file__).resolve().parents[1] / "src" / "openai_tts_gui" / "config.py"
    ).read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" in utils_source
    assert "OPENAI_BASE_URL" in config_source
    assert "TTS_PARALLELISM" in config_source
    assert "TTS_STREAM_FORMAT" in config_source


def test_presets_format_roundtrip(tmp_path):
    presets: dict[str, str] = {
        "dramatic": "Speak with gravitas and gravitas.",
        "cheerful": "Be upbeat and energetic!",
    }
    dest = tmp_path / "presets.json"
    save_presets(presets, filename=str(dest))
    loaded = load_presets(filename=str(dest))
    assert loaded == presets


def test_obfuscation_roundtrip():
    original = "sk-test-1234567890abcdef"
    encrypted = encrypt_key(original)
    assert encrypted != original
    assert encrypted != ""
    decrypted = decrypt_key(encrypted)
    assert decrypted == original
