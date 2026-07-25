"""Backward-compat TTSProcessor - wraps TTSWorker for old test/consumer code."""

from ..gui import TTSWorker


class TTSProcessor(TTSWorker):
    pass
