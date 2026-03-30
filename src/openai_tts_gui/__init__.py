from __future__ import annotations

from importlib import metadata

from .errors import (
    ConfigError,
    FFmpegError,
    FFmpegNotFoundError,
    TTSAPIError,
    TTSCancelledError,
    TTSChunkError,
    TTSError,
)

DEFAULT_APP_VERSION = "1.2.0"


def _resolve_package_version() -> str:
    try:
        return metadata.version("OpenAI_TTS_GUI")
    except metadata.PackageNotFoundError:
        return DEFAULT_APP_VERSION
    except Exception:
        return DEFAULT_APP_VERSION


__version__ = _resolve_package_version()

__all__ = [
    "ConfigError",
    "FFmpegError",
    "FFmpegNotFoundError",
    "TTSAPIError",
    "TTSCancelledError",
    "TTSChunkError",
    "TTSError",
    "TTSService",
    "preflight_check",
    "split_text",
]


def __getattr__(name: str):
    if name == "TTSService":
        from .tts import TTSService

        return TTSService
    if name == "preflight_check":
        from .core.ffmpeg import preflight_check

        return preflight_check
    if name == "split_text":
        from .core.text import split_text

        return split_text
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
