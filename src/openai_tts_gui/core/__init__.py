__all__ = [
    "cleanup_files",
    "concatenate_audio_files",
    "get_ffmpeg_version",
    "parse_ffmpeg_semver",
    "preflight_check",
    "sha256_text",
    "split_text",
    "write_sidecar_metadata",
]


def __getattr__(name: str):
    if name in {"cleanup_files", "concatenate_audio_files"}:
        from .audio import cleanup_files, concatenate_audio_files

        return {
            "cleanup_files": cleanup_files,
            "concatenate_audio_files": concatenate_audio_files,
        }[name]
    if name in {"get_ffmpeg_version", "parse_ffmpeg_semver", "preflight_check"}:
        from .ffmpeg import get_ffmpeg_version, parse_ffmpeg_semver, preflight_check

        return {
            "get_ffmpeg_version": get_ffmpeg_version,
            "parse_ffmpeg_semver": parse_ffmpeg_semver,
            "preflight_check": preflight_check,
        }[name]
    if name in {"sha256_text", "write_sidecar_metadata"}:
        from .metadata import sha256_text, write_sidecar_metadata

        return {
            "sha256_text": sha256_text,
            "write_sidecar_metadata": write_sidecar_metadata,
        }[name]
    if name == "split_text":
        from .text import split_text

        return split_text
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
