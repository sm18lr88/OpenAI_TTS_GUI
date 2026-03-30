from __future__ import annotations

__all__ = [
    "TTSProcessor",
    "TTSService",
    "compute_backoff",
]


def __getattr__(name: str):
    if name in {"TTSService", "compute_backoff", "_compute_backoff"}:
        from ._service import TTSService, compute_backoff

        return {
            "TTSService": TTSService,
            "compute_backoff": compute_backoff,
            "_compute_backoff": compute_backoff,
        }[name]
    if name == "TTSProcessor":
        from ._compat import TTSProcessor

        return TTSProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
