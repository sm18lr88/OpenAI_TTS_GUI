from __future__ import annotations

import pytest

from openai_tts_gui.core import text
from openai_tts_gui.errors import ConfigError


@pytest.mark.parametrize("chunk_size", [-1, 0])
def test_split_text_rejects_non_positive_chunk_sizes(chunk_size: int) -> None:
    with pytest.raises(ConfigError, match="positive integer"):
        text.split_text("hello", chunk_size)


@pytest.mark.parametrize("value", ["", "exact"])
def test_split_text_keeps_empty_and_exact_size_values(value: str) -> None:
    expected = [] if not value else [value]

    assert text.split_text(value, len(value) or 1) == expected


@pytest.mark.parametrize(
    ("value", "end_pos", "expected"),
    [
        ("alpha beta", 10, 6),
        ("alpha\tbeta", 10, 6),
        ("alpha\nbeta", 10, 6),
        ("alpha.", 6, 6),
        ("alpha.\rbeta", 7, 6),
        ("alpha?\rbeta", 7, 6),
        ("alpha!\rbeta", 7, 6),
        ("alpha;\rbeta", 7, 6),
        ("alpha:\rbeta", 7, 6),
    ],
)
def test_find_split_offset_prefers_supported_boundaries(
    value: str, end_pos: int, expected: int
) -> None:
    assert text._find_split_offset(value, 0, end_pos) == expected


def test_find_split_offset_rejects_punctuation_without_following_whitespace() -> None:
    assert text._find_split_offset("alpha.beta", 0, 7) == -1


def test_split_text_preserves_sentence_and_final_remainder() -> None:
    value = "alpha. beta gamma"

    chunks = text.split_text(value, 7)

    assert chunks == ["alpha. ", "beta ", "gamma"]
    assert "".join(chunks) == value


def test_split_text_splits_oversized_paragraph_at_newline() -> None:
    value = "paragraph one\nparagraph two\nparagraph three"

    chunks = text.split_text(value, 15)

    assert chunks[0] == "paragraph one\n"
    assert "".join(chunks) == value
    assert all(len(chunk) <= 15 for chunk in chunks)


def test_split_text_forces_progress_for_unbroken_oversized_word() -> None:
    value = "abcdefghij"

    chunks = text.split_text(value, 4)

    assert chunks == ["abcd", "efgh", "ij"]
    assert "".join(chunks) == value


def test_split_text_exits_after_an_exact_final_chunk() -> None:
    assert text.split_text("abcdefgh", 4) == ["abcd", "efgh"]
