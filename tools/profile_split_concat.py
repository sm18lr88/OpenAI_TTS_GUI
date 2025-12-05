"""
Small, network-free workload to profile CPU/IO paths:
- split_text on large input
- synthesize several WAVs and concatenate via ffmpeg
Generates output under a temp directory and cleans up on exit.
"""

from __future__ import annotations

import math
import os
import random
import struct
import tempfile
import wave
from pathlib import Path

from openai_tts_gui import config
from openai_tts_gui.utils import concatenate_audio_files, split_text


def _mk_text(chars=400_000) -> str:
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit"]
    punct = [".", "!", "?", ":", ";", ""]
    avg_len = 6  # rough average per token with punctuation
    needed = max(1, chars // avg_len)
    parts = [f"{random.choice(words)}{random.choice(punct)}" for _ in range(needed)]
    text = " ".join(parts)
    # Ensure we slightly exceed the requested length to avoid undershoot
    if len(text) < chars:
        extra = [f"{random.choice(words)}{random.choice(punct)}" for _ in range(needed // 10 + 1)]
        text = " ".join(parts + extra)
    return text[: chars + 128]  # small cushion


def _sine_wav(path: str, seconds: float = 0.05, freq: float = 440.0, rate: int = 48000) -> None:
    frames = int(seconds * rate)
    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for n in range(frames):
            val = int(32767 * math.sin(2 * math.pi * freq * (n / rate)))
            w.writeframesraw(struct.pack("<hh", val, val))


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Exercise splitter
        text = _mk_text(chars=500_000)
        chunks = split_text(text, config.MAX_CHUNK_SIZE)
        assert "".join(chunks).strip() == text.strip()
        # Exercise concat path with small synthetic WAVs
        inputs = []
        for i in range(8):
            f = td_path / f"p{i}.wav"
            _sine_wav(str(f), seconds=0.04 + i * 0.01)
            inputs.append(str(f))
        out = td_path / "out.wav"
        concatenate_audio_files(inputs, str(out))
        assert out.exists()
        # Keep temp directory around if needed by setting env KEEP_PROFILE_TMP=1
        if os.environ.get("KEEP_PROFILE_TMP") == "1":
            print(f"Profile artifacts preserved at: {td}")
        else:
            # normal TemporaryDirectory cleans up on exit
            pass


if __name__ == "__main__":
    main()
