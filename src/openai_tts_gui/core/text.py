from __future__ import annotations

import logging

from ..config import settings
from ..errors import ConfigError

logger = logging.getLogger(__name__)

_WHITESPACE_BOUNDARIES = frozenset({" ", "\t", "\n"})
_PUNCTUATION_BOUNDARIES = frozenset({".", "?", "!", ";", ":"})


def _find_split_offset(
    text: str,
    current_pos: int,
    end_pos: int,
) -> int:
    for index in range(end_pos - 1, current_pos - 1, -1):
        char = text[index]
        if char in _WHITESPACE_BOUNDARIES:
            return index + 1 - current_pos
        if char in _PUNCTUATION_BOUNDARIES and (
            index + 1 == end_pos or text[index + 1].isspace()
        ):
            return index + 1 - current_pos

    return -1


def split_text(text: str, chunk_size: int = settings.MAX_CHUNK_SIZE) -> list[str]:
    """Split text into chunks while preserving the original string exactly."""
    if chunk_size <= 0:
        raise ConfigError("chunk_size must be a positive integer.")
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    logger.debug("Splitting text of length %d with chunk_size %d", len(text), chunk_size)

    chunks: list[str] = []
    current_pos = 0
    text_len = len(text)

    while current_pos < text_len:
        end_pos = min(current_pos + chunk_size, text_len)
        window = text[current_pos:end_pos]

        if end_pos >= text_len:
            chunks.append(window)
            break

        chosen_split = _find_split_offset(text, current_pos, end_pos)
        if chosen_split <= 0:
            chosen_split = chunk_size
            logger.warning(
                "Forced split at index %d without a natural boundary.",
                current_pos + chosen_split,
            )

        final_chunk = text[current_pos : current_pos + chosen_split]
        if not final_chunk:
            raise ConfigError("split_text failed to make progress while chunking text.")
        chunks.append(final_chunk)
        current_pos += len(final_chunk)

    logger.debug("Text split into %d chunks", len(chunks))
    return chunks
