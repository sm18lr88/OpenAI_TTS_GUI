import random

import pytest

import config
from utils import split_text


def test_empty_returns_empty_list():
    assert split_text("", 10) == []


def test_small_text_single_chunk():
    text = "Hello world."
    chunks = split_text(text, 4096)
    assert chunks == [text]


@pytest.mark.parametrize("chunk_size", [8, 16, 64, 128])
def test_rejoin_equals_original(chunk_size):
    text = "Hello world! This is a test… 🚀 Newlines?\nYes!\nEnd."
    chunks = split_text(text, chunk_size=chunk_size)
    # Re-join exactly (no normalization): split_text trims leading whitespace across boundaries
    # so we allow a relaxed comparison that ignores leading whitespace in chunks.
    assert "".join(chunks).strip() == text.strip()
    assert all(len(c) <= chunk_size or c == chunks[-1] for c in chunks)


def test_no_space_long_token_forced_splits():
    long = "A" * (config.MAX_CHUNK_SIZE * 2 + 123)
    chunks = split_text(long, config.MAX_CHUNK_SIZE)
    # All chunks except maybe last must be exactly at the limit
    for c in chunks[:-1]:
        assert len(c) == config.MAX_CHUNK_SIZE
    assert "".join(chunks) == long


def test_sentence_boundaries_preferred():
    # Build a text with punctuation roughly every 40 chars
    parts = []
    for _i in range(20):
        s = " ".join(["word"] * 8) + random.choice([".", "!", "?", ";", ":"]) + " "
        parts.append(s)
    text = "".join(parts)
    chunks = split_text(text, 80)
    # Heuristic: many (not all) chunks should end with punctuation or space
    ratio = sum(1 for c in chunks if c[-1] in ".!?:; \n\t") / len(chunks)
    assert ratio >= 0.5
    assert "".join(chunks).strip() == text.strip()
