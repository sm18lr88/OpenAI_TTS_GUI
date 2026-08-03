"""Backward-compatible facade that re-exports newer module locations."""

from .core import (  # noqa: F401
    cleanup_files,
    concatenate_audio_files,
    get_ffmpeg_version,
    preflight_check,
    sha256_text,
    split_text,
    write_sidecar_metadata,
)
from .core import (
    parse_ffmpeg_semver as _parse_ffmpeg_semver,
)
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
