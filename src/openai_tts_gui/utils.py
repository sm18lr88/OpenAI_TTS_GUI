"""Backward-compat facade — re-exports from new module locations."""

from .core.audio import cleanup_files, concatenate_audio_files  # noqa: F401
from .core.ffmpeg import (  # noqa: F401
    get_ffmpeg_version,
    preflight_check,
)
from .core.ffmpeg import (
    parse_ffmpeg_semver as _parse_ffmpeg_semver,
)
from .core.metadata import sha256_text, write_sidecar_metadata  # noqa: F401
from .core.text import split_text  # noqa: F401
from .keystore import decrypt_key, encrypt_key, read_api_key, save_api_key  # noqa: F401
from .presets import load_presets, save_presets  # noqa: F401

__all__ = [
    "cleanup_files",
    "concatenate_audio_files",
    "decrypt_key",
    "encrypt_key",
    "get_ffmpeg_version",
    "load_presets",
    "preflight_check",
    "read_api_key",
    "save_api_key",
    "save_presets",
    "sha256_text",
    "split_text",
    "write_sidecar_metadata",
    "_parse_ffmpeg_semver",
]
