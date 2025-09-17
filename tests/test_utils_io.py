import contextlib
import math
import struct
import wave

from utils import concatenate_audio_files, read_api_key


def _sine_wav(path, seconds=0.1, freq=440.0, rate=48000):
    frames = int(seconds * rate)
    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for n in range(frames):
            val = int(32767 * math.sin(2 * math.pi * freq * (n / rate)))
            w.writeframesraw(struct.pack("<hh", val, val))


def test_concatenate_single_file_rename(tmp_path):
    src = tmp_path / "a.wav"
    out = tmp_path / "out.wav"
    _sine_wav(str(src), seconds=0.05)
    concatenate_audio_files([str(src)], str(out))
    assert out.exists()
    assert not src.exists()  # original is renamed to out
    with contextlib.closing(wave.open(str(out), "rb")) as w:
        assert w.getnchannels() == 2


def test_read_api_key_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "env_key")
    # Even if file exists, env var should win
    file = tmp_path / "api_key.enc"
    file.write_text("ignored\n", encoding="utf-8")
    monkeypatch.setattr("utils.config.API_KEY_FILE", str(file))
    assert read_api_key() == "env_key"
