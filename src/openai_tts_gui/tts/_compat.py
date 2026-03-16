"""Backward-compat TTSProcessor — wraps TTSWorker for old test/consumer code."""

from ..gui.workers import TTSWorker


class TTSProcessor(TTSWorker):
    pass
