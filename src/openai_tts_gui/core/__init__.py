__all__ = [
    "cleanup_files",
    "concatenate_audio_files",
    "get_ffmpeg_version",
    "parse_ffmpeg_semver",
    "preflight_check",
    "resolve_ffmpeg_command",
    "sha256_text",
    "split_text",
    "write_sidecar_metadata",
]


def __getattr__(name: str):
    if name in {"cleanup_files", "concatenate_audio_files", "own_ffmpeg_process"}:
        from .audio import cleanup_files, concatenate_audio_files, own_ffmpeg_process

        return {
            "cleanup_files": cleanup_files,
            "concatenate_audio_files": concatenate_audio_files,
            "own_ffmpeg_process": own_ffmpeg_process,
        }[name]
    if name in {
        "get_ffmpeg_version",
        "parse_ffmpeg_semver",
        "preflight_check",
        "resolve_ffmpeg_command",
    }:
        from .ffmpeg import (
            get_ffmpeg_version,
            parse_ffmpeg_semver,
            preflight_check,
            resolve_ffmpeg_command,
        )

        return {
            "get_ffmpeg_version": get_ffmpeg_version,
            "parse_ffmpeg_semver": parse_ffmpeg_semver,
            "preflight_check": preflight_check,
            "resolve_ffmpeg_command": resolve_ffmpeg_command,
        }[name]
    if name in {"sha256_text", "write_sidecar_metadata"}:
        from .metadata import sha256_text, write_sidecar_metadata

        return {
            "sha256_text": sha256_text,
            "write_sidecar_metadata": write_sidecar_metadata,
        }[name]
    sidecar_names = {
        "AudioIdentity",
        "AudioMismatch",
        "AudioVerified",
        "MissingAudio",
        "SidecarParseError",
        "SidecarRequestInput",
        "SidecarRequestMeta",
        "SidecarSettings",
        "SidecarV1",
        "SidecarV2",
        "SidecarWriteInput",
        "UnsupportedSidecarSchemaError",
        "build_sidecar_v2",
        "resolve_retained_directory",
        "verify_sidecar_audio",
    }
    if name in sidecar_names:
        from . import sidecar

        return getattr(sidecar, name)
    if name in {"parse_sidecar_metadata", "parse_sidecar_payload", "read_sidecar_metadata"}:
        from . import _sidecar_parse

        return getattr(_sidecar_parse, name)
    if name == "split_text":
        from .text import split_text

        return split_text
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
