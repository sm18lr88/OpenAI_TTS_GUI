import math
import os
import struct
import tempfile
import wave

import pytest

from utils import concatenate_audio_files, preflight_check, split_text


def test_chunker_roundtrip():
    text = "Hello world!  This is a test… 🚀 Newlines?\nYes!\nEnd."
    chunks = split_text(text, chunk_size=16)
    assert "".join(chunks).replace("  ", " ").strip() == text.replace("  ", " ").strip()
    assert all(len(c) <= 16 or c == chunks[-1] for c in chunks)


def _sine_wav(path, seconds=0.2, freq=440.0, rate=48000):
    frames = int(seconds * rate)
    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for n in range(frames):
            val = int(32767 * math.sin(2 * math.pi * freq * (n / rate)))
            frame = struct.pack("<hh", val, val)
            w.writeframesraw(frame)


@pytest.mark.skipif(not preflight_check()[0], reason="ffmpeg not available")
def test_concat_duration_close():
    with tempfile.TemporaryDirectory() as td:
        f1 = os.path.join(td, "a.wav")
        f2 = os.path.join(td, "b.wav")
        out = os.path.join(td, "out.wav")
        _sine_wav(f1, seconds=0.20)
        _sine_wav(f2, seconds=0.30)
        concatenate_audio_files([f1, f2], out)
        with wave.open(out, "r") as w:
            dur = w.getnframes() / w.getframerate()
        assert 0.49 <= dur <= 0.52
