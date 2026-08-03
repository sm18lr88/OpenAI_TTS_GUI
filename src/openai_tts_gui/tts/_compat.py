"""Backward-compatible TTSProcessor that wraps TTSWorker for older tests and consumers."""

from ..gui import TTSWorker


class TTSProcessor(TTSWorker):
    pass
