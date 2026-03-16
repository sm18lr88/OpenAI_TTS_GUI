import logging
import re

from ..config import settings

logger = logging.getLogger(__name__)

_BOUNDARY_RE = re.compile(r"[\.?!;:](?=\s|$)")


def split_text(text, chunk_size=settings.MAX_CHUNK_SIZE):
    logger.debug(f"Splitting text of length {len(text)} with chunk_size {chunk_size}")
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current_pos = 0
    text_len = len(text)

    while current_pos < text_len:
        end_pos = min(current_pos + chunk_size, text_len)
        chunk = text[current_pos:end_pos]

        if end_pos == text_len:
            chunks.append(chunk)
            break

        split_index = -1
        punct_match = None
        for m in _BOUNDARY_RE.finditer(chunk):
            punct_match = m
        if punct_match:
            split_index = punct_match.end()

        if split_index == -1:
            split_index = chunk.rfind(" ") + 1
            if split_index == 0:
                split_index = chunk_size
                logger.warning(
                    f"Forced split at index {current_pos + split_index} without space/punctuation"
                )

        final_chunk = text[current_pos : current_pos + split_index]
        chunks.append(final_chunk)
        current_pos += len(final_chunk)

    logger.debug(f"Text split into {len(chunks)} chunks")
    return chunks
