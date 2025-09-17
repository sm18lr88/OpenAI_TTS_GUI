import math
import random
import struct
import wave

import pytest

import config
from utils import concatenate_audio_files, split_text


def _mk_text(chars=200_000):
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit"]
    parts = []
    while len(" ".join(parts)) < chars:
        parts.append(random.choice(words) + random.choice([".", "!", "?", ":", ";", ""]))
    return " ".join(parts)


def _sine_wav(path, seconds=0.05, freq=440.0, rate=48000):
    frames = int(seconds * rate)
    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        for n in range(frames):
            val = int(32767 * math.sin(2 * math.pi * freq * (n / rate)))
            w.writeframesraw(struct.pack("<hh", val, val))


@pytest.mark.benchmark(group="split_text")
def test_bench_split_text_large(benchmark):
    text = _mk_text(chars=300_000)
    benchmark(split_text, text, config.MAX_CHUNK_SIZE)


@pytest.mark.benchmark(group="concat")
def test_bench_concat_small_files(benchmark, tmp_path):
    inputs = []
    for i in range(5):
        f = tmp_path / f"p{i}.wav"
        _sine_wav(str(f), seconds=0.03 + i * 0.01)
        inputs.append(str(f))
    out = tmp_path / "out.wav"
    benchmark(concatenate_audio_files, inputs, str(out))
    assert out.exists()
