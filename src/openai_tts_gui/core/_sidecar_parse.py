from __future__ import annotations

import json
from pathlib import Path

from .sidecar import (
    AudioIdentity,
    ParsedSidecar,
    SidecarParseError,
    SidecarRequestMeta,
    SidecarSettings,
    SidecarV1,
    SidecarV2,
    UnsupportedSidecarSchemaError,
    _basename,
    _safe_environment,
    _safe_retry_headers,
)

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def parse_sidecar_metadata(source: str | Path) -> ParsedSidecar:
    match source:
        case Path() as path:
            return read_sidecar_metadata(path)
        case str() as serialized:
            return _parse_serialized(serialized)


def _parse_serialized(serialized: str) -> ParsedSidecar:
    try:
        payload = json.loads(serialized)
    except json.JSONDecodeError as exc:
        raise SidecarParseError("the sidecar is not valid JSON") from exc
    return parse_sidecar_payload(payload)


def read_sidecar_metadata(path: Path) -> ParsedSidecar:
    try:
        return _parse_serialized(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError) as exc:
        raise SidecarParseError("could not read the sidecar file") from exc


def parse_sidecar_payload(payload: JsonValue) -> ParsedSidecar:
    source = _mapping(payload, "root")
    match source.get("schema_version"):
        case None:
            return _parse_v1(source)
        case 2:
            return _parse_v2(source)
        case int() as unsupported:
            raise UnsupportedSidecarSchemaError(unsupported)
        case _:
            raise SidecarParseError("schema_version must be an integer")


def _parse_v1(source: dict[str, JsonValue]) -> SidecarV1:
    request_ids: list[str] = []
    for item in _list(source.get("request_meta"), "request_meta"):
        match _mapping(item, "request_meta entry").get("request_id"):
            case None:
                continue
            case str() as value if value:
                if value not in request_ids:
                    request_ids.append(value)
            case _:
                raise SidecarParseError("request_id must be a string")
    match source.get("parallelism_used"):
        case None:
            return SidecarV1(tuple(request_ids), None)
        case int() as value if type(value) is int:
            return SidecarV1(tuple(request_ids), value)
        case _:
            raise SidecarParseError("parallelism_used must be an integer")


def _parse_v2(source: dict[str, JsonValue]) -> SidecarV2:
    required = {
        "schema_version",
        "audio",
        "settings",
        "environment",
        "retained_directory",
        "request_meta",
    }
    if set(source) != required:
        raise SidecarParseError("the v2 sidecar fields are invalid")
    return SidecarV2(
        audio=_parse_audio(_mapping(source["audio"], "audio")),
        settings=_parse_settings(_mapping(source["settings"], "settings")),
        environment=_parse_environment(_mapping(source["environment"], "environment")),
        retained_directory=_parse_retained_directory(source["retained_directory"]),
        request_meta=tuple(
            _parse_request_meta(item) for item in _list(source["request_meta"], "request_meta")
        ),
    )


def _parse_audio(source: dict[str, JsonValue]) -> AudioIdentity:
    if set(source) != {"basename", "size_bytes", "sha256"}:
        raise SidecarParseError("the audio fields are invalid")
    audio_basename = _string(source["basename"], "audio.basename")
    size_bytes = _integer(source["size_bytes"], "audio.size_bytes")
    sha256 = _string(source["sha256"], "audio.sha256")
    if _basename(audio_basename) != audio_basename or size_bytes < 0 or not _sha256(sha256):
        raise SidecarParseError("the audio identity is invalid")
    return AudioIdentity(audio_basename, size_bytes, sha256)


def _parse_settings(source: dict[str, JsonValue]) -> SidecarSettings:
    required = {
        "model",
        "voice",
        "response_format",
        "speed",
        "chunk_count",
        "chunk_size",
        "parallelism_requested",
        "parallelism_used",
        "stream_format",
        "retain_files",
        "input_chars",
    }
    if set(source) != required:
        raise SidecarParseError("the settings fields are invalid")
    match source["speed"]:
        case int() as value if type(value) is int:
            speed = float(value)
        case float() as value:
            speed = value
        case _:
            raise SidecarParseError("settings.speed must be numeric")
    return SidecarSettings(
        _string(source["model"], "settings.model"),
        _string(source["voice"], "settings.voice"),
        _string(source["response_format"], "settings.response_format"),
        speed,
        _integer(source["chunk_count"], "settings.chunk_count"),
        _integer(source["chunk_size"], "settings.chunk_size"),
        _integer(source["parallelism_requested"], "settings.parallelism_requested"),
        _integer(source["parallelism_used"], "settings.parallelism_used"),
        _string(source["stream_format"], "settings.stream_format"),
        _boolean(source["retain_files"], "settings.retain_files"),
        _integer(source["input_chars"], "settings.input_chars"),
    )


def _parse_environment(source: dict[str, JsonValue]) -> tuple[tuple[str, str], ...]:
    return _safe_environment(
        {key: _string(value, f"environment.{key}") for key, value in source.items()}
    )


def _parse_retained_directory(value: JsonValue) -> str | None:
    match value:
        case None:
            return None
        case str() as name if _basename(name) == name:
            return name
        case _:
            raise SidecarParseError("retained_directory must be a basename or null")


def _parse_request_meta(value: JsonValue) -> SidecarRequestMeta:
    source = _mapping(value, "request_meta entry")
    required = {
        "chunk_index",
        "request_id",
        "model_header",
        "file",
        "attempts",
        "characters",
        "retry_headers",
    }
    if set(source) != required:
        raise SidecarParseError("the request_meta fields are invalid")
    file = _string(source["file"], "file")
    if _basename(file) != file:
        raise SidecarParseError("the chunk file name must be a basename")
    return SidecarRequestMeta(
        _integer(source["chunk_index"], "chunk_index"),
        _nullable_string(source["request_id"], "request_id"),
        _nullable_string(source["model_header"], "model_header"),
        file,
        _integer(source["attempts"], "attempts"),
        _integer(source["characters"], "characters"),
        _nullable_headers(source["retry_headers"]),
    )


def _mapping(value: JsonValue, name: str) -> dict[str, JsonValue]:
    match value:
        case dict() as mapping:
            return mapping
        case _:
            raise SidecarParseError(f"{name} must be an object")


def _list(value: JsonValue | None, name: str) -> list[JsonValue]:
    match value:
        case list() as values:
            return values
        case _:
            raise SidecarParseError(f"{name} must be a list")


def _string(value: JsonValue, name: str) -> str:
    match value:
        case str() as text:
            return text
        case _:
            raise SidecarParseError(f"{name} must be a string")


def _nullable_string(value: JsonValue, name: str) -> str | None:
    match value:
        case None:
            return None
        case str() as text:
            return text
        case _:
            raise SidecarParseError(f"{name} must be a string or null")


def _integer(value: JsonValue, name: str) -> int:
    match value:
        case int() as integer if type(integer) is int:
            return integer
        case _:
            raise SidecarParseError(f"{name} must be an integer")


def _boolean(value: JsonValue, name: str) -> bool:
    match value:
        case bool() as boolean:
            return boolean
        case _:
            raise SidecarParseError(f"{name} must be boolean")


def _nullable_headers(value: JsonValue) -> tuple[tuple[str, str], ...] | None:
    match value:
        case None:
            return None
        case dict() as headers:
            return _safe_retry_headers(
                {key: _string(item, "retry_headers value") for key, item in headers.items()}
            )
        case _:
            raise SidecarParseError("retry_headers must be an object or null")


def _sha256(value: str) -> bool:
    return (
        len(value) == 64
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )
